import { contentPlatforms, musicPlatforms, type Support } from '@/lib/platforms'

function Mark({ value }: { value: Support }) {
  if (value === true) return <span title="支持">✅</span>
  if (value === false) return <span title="尚未适配">❌</span>
  return <span title="平台暂无此类内容">🚫</span>
}

function Name({ name, color }: { name: string; color: string }) {
  return (
    <span className="inline-flex items-center gap-2 font-medium">
      <span className="size-2.5 shrink-0 rounded-full" style={{ background: color }} />
      {name}
    </span>
  )
}

export function PlatformMatrix({ kind = 'content' }: { kind?: 'content' | 'music' }) {
  if (kind === 'music') {
    return (
      <table>
        <thead>
          <tr>
            <th>平台</th>
            <th className="text-center!">音频</th>
            <th className="text-center!">评论区渲染</th>
          </tr>
        </thead>
        <tbody>
          {musicPlatforms.map((p) => (
            <tr key={p.id}>
              <td>
                <Name name={p.name} color={p.color} />
              </td>
              <td className="text-center">
                <Mark value={p.audio} />
              </td>
              <td className="text-center">
                <Mark value={p.comments} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    )
  }

  return (
    <table>
      <thead>
        <tr>
          <th>平台</th>
          <th>配置 ID</th>
          <th className="text-center!">图文</th>
          <th className="text-center!">评论区</th>
          <th className="text-center!">视频</th>
          <th className="text-center!">Live Photo</th>
        </tr>
      </thead>
      <tbody>
        {contentPlatforms.map((p) => (
          <tr key={p.id}>
            <td>
              <Name name={p.name} color={p.color} />
            </td>
            <td>
              <code>{p.id}</code>
            </td>
            <td className="text-center">
              <Mark value={p.graphic} />
            </td>
            <td className="text-center">
              <Mark value={p.comments} />
            </td>
            <td className="text-center">
              <Mark value={p.video} />
            </td>
            <td className="text-center">
              <Mark value={p.livePhoto} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
