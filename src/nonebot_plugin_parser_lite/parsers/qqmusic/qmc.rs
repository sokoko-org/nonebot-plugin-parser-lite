use std::fs::{File, OpenOptions};
use std::io::{BufReader, BufWriter, Read, Seek, SeekFrom, Write};
use std::path::Path;

use base64::{engine::general_purpose::STANDARD, Engine as _};
use pyo3::exceptions::{PyOSError, PyValueError};
use pyo3::prelude::*;

const QMC_V2_KEY_PREFIX: &[u8] = b"QQMusic EncV2,Key:";
const RC4_FIRST_SEGMENT_SIZE: usize = 128;
const RC4_SEGMENT_SIZE: usize = 5120;

const QMC_V2_DERIVE_KEY_1: [u8; 16] = [
    0x33, 0x38, 0x36, 0x5A, 0x4A, 0x59, 0x21, 0x40, 0x23, 0x2A, 0x24, 0x25, 0x5E, 0x26, 0x29, 0x28,
];
const QMC_V2_DERIVE_KEY_2: [u8; 16] = [
    0x2A, 0x2A, 0x23, 0x21, 0x28, 0x23, 0x24, 0x25, 0x26, 0x5E, 0x61, 0x31, 0x63, 0x5A, 0x2C, 0x54,
];

#[derive(Debug)]
enum QmcError {
    Value(String),
    Io(std::io::Error),
}

impl std::fmt::Display for QmcError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Value(message) => f.write_str(message),
            Self::Io(error) => write!(f, "{error}"),
        }
    }
}

impl std::error::Error for QmcError {}

impl From<std::io::Error> for QmcError {
    fn from(value: std::io::Error) -> Self {
        Self::Io(value)
    }
}

impl From<base64::DecodeError> for QmcError {
    fn from(value: base64::DecodeError) -> Self {
        Self::Value(value.to_string())
    }
}

impl From<QmcError> for PyErr {
    fn from(value: QmcError) -> Self {
        match value {
            QmcError::Value(message) => PyValueError::new_err(message),
            QmcError::Io(error) => PyOSError::new_err(error.to_string()),
        }
    }
}

fn simple_make_key(salt: usize, length: usize) -> Vec<u8> {
    let mut key = vec![0u8; length];
    for (index, item) in key.iter_mut().enumerate() {
        *item = ((f64::tan(salt as f64 + index as f64 * 0.1).abs() * 100.0) as u64 & 0xFF) as u8;
    }
    key
}

fn tea_decrypt_block(block: &[u8], key: &[u8]) -> Result<[u8; 8], QmcError> {
    let mut v0 = u32::from_be_bytes(
        block[0..4]
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea block".to_string()))?,
    );
    let mut v1 = u32::from_be_bytes(
        block[4..8]
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea block".to_string()))?,
    );
    let k0 = u32::from_be_bytes(
        key[0..4]
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea key".to_string()))?,
    );
    let k1 = u32::from_be_bytes(
        key[4..8]
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea key".to_string()))?,
    );
    let k2 = u32::from_be_bytes(
        key[8..12]
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea key".to_string()))?,
    );
    let k3 = u32::from_be_bytes(
        key[12..16]
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea key".to_string()))?,
    );

    let delta = 0x9E37_79B9u32;
    let mut sum_value = delta.wrapping_mul(16);
    for _ in 0..16 {
        v1 = v1.wrapping_sub(
            ((v0 << 4).wrapping_add(k2))
                ^ (v0.wrapping_add(sum_value))
                ^ ((v0 >> 5).wrapping_add(k3)),
        );
        v0 = v0.wrapping_sub(
            ((v1 << 4).wrapping_add(k0))
                ^ (v1.wrapping_add(sum_value))
                ^ ((v1 >> 5).wrapping_add(k1)),
        );
        sum_value = sum_value.wrapping_sub(delta);
    }

    let mut output = [0u8; 8];
    output[0..4].copy_from_slice(&v0.to_be_bytes());
    output[4..8].copy_from_slice(&v1.to_be_bytes());
    Ok(output)
}

fn xor_8_bytes(left: &[u8; 8], right: &[u8; 8]) -> [u8; 8] {
    let mut output = [0u8; 8];
    for index in 0..8 {
        output[index] = left[index] ^ right[index];
    }
    output
}

fn decrypt_tencent_tea(input_buffer: &[u8], key: &[u8]) -> Result<Vec<u8>, QmcError> {
    const SALT_LEN: usize = 2;
    const ZERO_LEN: usize = 7;

    if input_buffer.len() % 8 != 0 {
        return Err(QmcError::Value(
            "inBuf size not a multiple of the block size".to_string(),
        ));
    }
    if input_buffer.len() < 16 {
        return Err(QmcError::Value("inBuf size too small".to_string()));
    }

    let mut decrypted_block = tea_decrypt_block(&input_buffer[..8], key)?;
    let pad_len = (decrypted_block[0] & 0x7) as usize;
    let output_len = input_buffer.len() - 1 - pad_len - SALT_LEN - ZERO_LEN;
    let mut output = vec![0u8; output_len];

    let mut iv_prev = [0u8; 8];
    let mut iv_cur: [u8; 8] = input_buffer[..8]
        .try_into()
        .map_err(|_| QmcError::Value("invalid tea input".to_string()))?;
    let mut input_pos = 8usize;
    let mut dest_idx = 1 + pad_len;

    let decrypt_next_block = |decrypted_block: &mut [u8; 8],
                              iv_prev: &mut [u8; 8],
                              iv_cur: &mut [u8; 8],
                              input_pos: &mut usize,
                              dest_idx: &mut usize|
     -> Result<(), QmcError> {
        *iv_prev = *iv_cur;
        let next_block: [u8; 8] = input_buffer
            .get(*input_pos..*input_pos + 8)
            .ok_or_else(|| QmcError::Value("unexpected end of tea buffer".to_string()))?
            .try_into()
            .map_err(|_| QmcError::Value("invalid tea buffer block".to_string()))?;
        *iv_cur = next_block;
        let xored = xor_8_bytes(decrypted_block, iv_cur);
        *decrypted_block = tea_decrypt_block(&xored, key)?;
        *input_pos += 8;
        *dest_idx = 0;
        Ok(())
    };

    let mut salt_index = 1usize;
    while salt_index <= SALT_LEN {
        if dest_idx < 8 {
            dest_idx += 1;
            salt_index += 1;
        } else {
            decrypt_next_block(
                &mut decrypted_block,
                &mut iv_prev,
                &mut iv_cur,
                &mut input_pos,
                &mut dest_idx,
            )?;
        }
    }

    let mut output_pos = 0usize;
    while output_pos < output_len {
        if dest_idx < 8 {
            output[output_pos] = decrypted_block[dest_idx] ^ iv_prev[dest_idx];
            dest_idx += 1;
            output_pos += 1;
        } else {
            decrypt_next_block(
                &mut decrypted_block,
                &mut iv_prev,
                &mut iv_cur,
                &mut input_pos,
                &mut dest_idx,
            )?;
        }
    }

    let mut zero_index = 1usize;
    while zero_index <= ZERO_LEN {
        if dest_idx < 8 {
            if decrypted_block[dest_idx] != iv_prev[dest_idx] {
                return Err(QmcError::Value("zero check failed".to_string()));
            }
            dest_idx += 1;
            zero_index += 1;
        } else {
            decrypt_next_block(
                &mut decrypted_block,
                &mut iv_prev,
                &mut iv_cur,
                &mut input_pos,
                &mut dest_idx,
            )?;
        }
    }

    Ok(output)
}

fn derive_key_v1(raw_key_decoded: &[u8]) -> Result<Vec<u8>, QmcError> {
    if raw_key_decoded.len() < 16 {
        return Err(QmcError::Value("key length is too short".to_string()));
    }

    let simple_key = simple_make_key(106, 8);
    let mut tea_key = vec![0u8; 16];
    for index in 0..8 {
        tea_key[index << 1] = simple_key[index];
        tea_key[(index << 1) + 1] = raw_key_decoded[index];
    }

    let decrypted = decrypt_tencent_tea(&raw_key_decoded[8..], &tea_key)?;
    let mut output = raw_key_decoded[..8].to_vec();
    output.extend_from_slice(&decrypted);
    Ok(output)
}

fn derive_key_v2(raw_key: &[u8]) -> Result<Vec<u8>, QmcError> {
    let buffer = decrypt_tencent_tea(raw_key, &QMC_V2_DERIVE_KEY_1)?;
    let buffer = decrypt_tencent_tea(&buffer, &QMC_V2_DERIVE_KEY_2)?;
    STANDARD.decode(buffer).map_err(Into::into)
}

fn derive_qmc_key(raw_key: &[u8]) -> Result<Vec<u8>, QmcError> {
    let mut decoded = STANDARD.decode(raw_key)?;
    if decoded.starts_with(QMC_V2_KEY_PREFIX) {
        decoded = derive_key_v2(&decoded[QMC_V2_KEY_PREFIX.len()..])?;
    }
    derive_key_v1(&decoded)
}

struct MapCipher {
    key: Vec<u8>,
    size: usize,
}

impl MapCipher {
    fn new(key: Vec<u8>) -> Result<Self, QmcError> {
        if key.is_empty() {
            return Err(QmcError::Value(
                "qmc map cipher key cannot be empty".to_string(),
            ));
        }
        let size = key.len();
        Ok(Self { key, size })
    }

    fn rotate(value: u8, bits: u8) -> u8 {
        let rotate = (bits + 4) % 8;
        value.wrapping_shl(rotate as u32) | value.wrapping_shr(rotate as u32)
    }

    fn get_mask(&self, offset: usize) -> u8 {
        let normalized_offset = if offset > 0x7FFF {
            offset % 0x7FFF
        } else {
            offset
        };
        let index = (((normalized_offset as u128 * normalized_offset as u128) + 71_214)
            % self.size as u128) as usize;
        Self::rotate(self.key[index], (index & 0x7) as u8)
    }

    fn decrypt(&self, buffer: &mut [u8], offset: usize) {
        for (index, item) in buffer.iter_mut().enumerate() {
            *item ^= self.get_mask(offset + index);
        }
    }
}

struct Rc4Cipher {
    key: Vec<u8>,
    size: usize,
    box_state: Vec<u8>,
    hash: u32,
}

impl Rc4Cipher {
    fn new(key: Vec<u8>) -> Result<Self, QmcError> {
        if key.is_empty() {
            return Err(QmcError::Value(
                "qmc rc4 cipher key cannot be empty".to_string(),
            ));
        }

        let size = key.len();
        let mut box_state = (0..size)
            .map(|index| (index & 0xFF) as u8)
            .collect::<Vec<_>>();
        let mut j = 0usize;
        for index in 0..size {
            j = (j + box_state[index] as usize + key[index % size] as usize) % size;
            box_state.swap(index, j);
        }

        let hash = Self::get_hash_base(&key);
        Ok(Self {
            key,
            size,
            box_state,
            hash,
        })
    }

    fn get_hash_base(key: &[u8]) -> u32 {
        let mut result = 1u32;
        for value in key {
            if *value == 0 {
                continue;
            }
            let next_hash = result.wrapping_mul(*value as u32);
            if next_hash == 0 || next_hash <= result {
                break;
            }
            result = next_hash;
        }
        result
    }

    fn get_segment_skip(&self, segment_id: usize) -> usize {
        let seed = self.key[segment_id % self.size] as usize;
        if seed == 0 {
            return 0;
        }
        let index = ((self.hash as f64 / ((segment_id + 1) * seed) as f64) * 100.0) as usize;
        index % self.size
    }

    fn decrypt_first_segment(&self, buffer: &mut [u8], offset: usize) {
        for (index, item) in buffer.iter_mut().enumerate() {
            *item ^= self.key[self.get_segment_skip(offset + index)];
        }
    }

    fn decrypt_segment(&self, buffer: &mut [u8], offset: usize) {
        let mut box_state = self.box_state.clone();
        let mut j = 0usize;
        let mut k = 0usize;
        let skip_length =
            (offset % RC4_SEGMENT_SIZE) + self.get_segment_skip(offset / RC4_SEGMENT_SIZE);

        for index in 0..(skip_length + buffer.len()) {
            j = (j + 1) % self.size;
            k = (box_state[j] as usize + k) % self.size;
            box_state.swap(j, k);
            if index >= skip_length {
                let output_index = index - skip_length;
                let xor_index = (box_state[j] as usize + box_state[k] as usize) % self.size;
                buffer[output_index] ^= box_state[xor_index];
            }
        }
    }

    fn decrypt(&self, buffer: &mut [u8], mut offset: usize) {
        let mut to_process = buffer.len();
        let mut processed = 0usize;

        if offset < RC4_FIRST_SEGMENT_SIZE {
            let block_size = to_process.min(RC4_FIRST_SEGMENT_SIZE - offset);
            self.decrypt_first_segment(&mut buffer[..block_size], offset);
            offset += block_size;
            to_process -= block_size;
            processed += block_size;
            if to_process == 0 {
                return;
            }
        }

        if offset % RC4_SEGMENT_SIZE != 0 {
            let block_size = to_process.min(RC4_SEGMENT_SIZE - offset % RC4_SEGMENT_SIZE);
            self.decrypt_segment(&mut buffer[processed..processed + block_size], offset);
            offset += block_size;
            to_process -= block_size;
            processed += block_size;
            if to_process == 0 {
                return;
            }
        }

        while to_process > RC4_SEGMENT_SIZE {
            self.decrypt_segment(&mut buffer[processed..processed + RC4_SEGMENT_SIZE], offset);
            offset += RC4_SEGMENT_SIZE;
            to_process -= RC4_SEGMENT_SIZE;
            processed += RC4_SEGMENT_SIZE;
        }

        if to_process > 0 {
            self.decrypt_segment(&mut buffer[processed..], offset);
        }
    }
}

enum QmcCipher {
    Map(MapCipher),
    Rc4(Rc4Cipher),
}

impl QmcCipher {
    fn decrypt(&self, buffer: &mut [u8], offset: usize) {
        match self {
            Self::Map(cipher) => cipher.decrypt(buffer, offset),
            Self::Rc4(cipher) => cipher.decrypt(buffer, offset),
        }
    }
}

fn new_qmc_cipher(key: Vec<u8>) -> Result<QmcCipher, QmcError> {
    if key.len() > 300 {
        return Ok(QmcCipher::Rc4(Rc4Cipher::new(key)?));
    }
    if !key.is_empty() {
        return Ok(QmcCipher::Map(MapCipher::new(key)?));
    }
    Err(QmcError::Value("QMC key cannot be empty".to_string()))
}

fn crc(data: &[u8], bits: u32, polynomial: u32) -> u32 {
    let mut value = 0;
    let mask = (1 << bits) - 1;
    for byte in data {
        value ^= (*byte as u32) << (bits - 8);
        for _ in 0..8 {
            value = ((value << 1)
                ^ if value & (1 << (bits - 1)) != 0 {
                    polynomial
                } else {
                    0
                })
                & mask;
        }
    }
    value
}

fn flac_frame_samples(data: &[u8], fixed_block: u64) -> Option<(u64, u64)> {
    if data.len() < 7 || data[0] != 0xFF || data[1] & 0xFE != 0xF8 || data[3] & 1 != 0 {
        return None;
    }
    let mut pos = 4;
    let first = data[pos];
    let mut number;
    if first < 0x80 {
        number = first as u64;
        pos += 1;
    } else {
        let count = first.leading_ones() as usize;
        if !(2..=7).contains(&count) || data.len() <= pos + count {
            return None;
        }
        number = (first & (0x7F >> count)) as u64;
        for byte in &data[pos + 1..pos + count] {
            if byte & 0xC0 != 0x80 {
                return None;
            }
            number = (number << 6) | (byte & 0x3F) as u64;
        }
        pos += count;
    }
    let block_code = data[2] >> 4;
    let rate_code = data[2] & 0xF;
    if rate_code == 15 {
        return None;
    }
    let samples = match block_code {
        0 => return None,
        1 => 192,
        2..=5 => 576 << (block_code - 2),
        6 => {
            let samples = *data.get(pos)? as u64 + 1;
            pos += 1;
            samples
        }
        7 => {
            let samples = u16::from_be_bytes([*data.get(pos)?, *data.get(pos + 1)?]) as u64 + 1;
            pos += 2;
            samples
        }
        _ => 256 << (block_code - 8),
    };
    pos += match rate_code {
        12 => 1,
        13 | 14 => 2,
        _ => 0,
    };
    if crc(data.get(..pos + 1)?, 8, 0x07) != 0 {
        return None;
    }
    let start = if data[1] & 1 != 0 {
        number
    } else {
        number * fixed_block
    };
    Some((start, samples))
}

// 只在最后一帧的采样数与 CRC 均通过时去掉 QQMusic 的 30 字节尾部。
fn remove_flac_trailer(file: &mut File) -> Result<(), QmcError> {
    file.rewind()?;
    let mut header = Vec::with_capacity(42);
    file.take(42).read_to_end(&mut header)?;
    if header.len() != 42
        || &header[..4] != b"fLaC"
        || header[4] & 0x7F != 0
        || header[5..8] != [0, 0, 0x22]
    {
        return Ok(());
    }
    let info = &header[8..];
    let total_samples = u64::from_be_bytes(info[10..18].try_into().unwrap()) & ((1 << 36) - 1);
    let fixed_block = u16::from_be_bytes([info[2], info[3]]) as u64;
    let max_frame = u32::from_be_bytes([0, info[7], info[8], info[9]]) as u64;
    let max_frame = if max_frame == 0 { 1024 * 1024 } else { max_frame };
    let size = file.seek(SeekFrom::End(0))?;
    file.seek(SeekFrom::Start(size.saturating_sub(max_frame + 30).max(42)))?;
    let mut tail = Vec::new();
    file.read_to_end(&mut tail)?;
    for index in 0..tail.len().saturating_sub(30) {
        if tail[index] != 0xFF {
            continue;
        }
        let Some((start, samples)) = flac_frame_samples(&tail[index..], fixed_block) else {
            continue;
        };
        if start + samples != total_samples {
            continue;
        }
        if crc(&tail[index..], 16, 0x8005) == 0 {
            return Ok(());
        }
        if tail.len() - index > 32 && crc(&tail[index..tail.len() - 30], 16, 0x8005) == 0 {
            file.set_len(size - 30)?;
            return Ok(());
        }
    }
    Ok(())
}

fn decrypt_file(
    source_path: &str,
    target_path: &str,
    ekey: &str,
) -> Result<(), QmcError> {
    let cipher = new_qmc_cipher(derive_qmc_key(ekey.as_bytes())?)?;

    let mut reader = BufReader::new(File::open(Path::new(source_path))?);
    let mut writer = BufWriter::new(
        OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(true)
            .open(Path::new(target_path))?,
    );
    let mut offset = 0usize;
    let mut buffer = vec![0u8; 65536];

    loop {
        let read_size = reader.read(&mut buffer)?;
        if read_size == 0 {
            break;
        }
        let chunk = &mut buffer[..read_size];
        cipher.decrypt(chunk, offset);
        writer.write_all(chunk)?;
        offset += read_size;
    }

    let mut file = writer.into_inner().map_err(|error| error.into_error())?;
    remove_flac_trailer(&mut file)
}

#[pyfunction]
fn decrypt_qmc_file(
    py: Python<'_>,
    source_path: &str,
    target_path: &str,
    ekey: &str,
) -> PyResult<()> {
    py.detach(|| decrypt_file(source_path, target_path, ekey))
        .map_err(Into::into)
}

#[pymodule(gil_used = false)]
fn qmc(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(decrypt_qmc_file, module)?)?;
    Ok(())
}
