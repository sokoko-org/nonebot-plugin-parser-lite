from msgspec import Struct


class ModelResult(Struct):
    summary: str


class AIConclusion(Struct):
    model_result: ModelResult | None = None

    @property
    def summary(self) -> str:
        if self.model_result and self.model_result.summary:
            return self.model_result.summary
        return "该视频暂不支持AI总结"
