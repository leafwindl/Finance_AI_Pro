class UpstreamServiceError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 502,
        code: str = "upstream_error",
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.retryable = retryable


class ClientError(Exception):
    """客户端可判定错误：全局 handler 渲染为 {error:{code,message,retryable}}。

    契约 §4：同步可判定的错误（校验失败 / 无权 / 状态冲突等）统一走此异常。
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        code: str = "invalid_request",
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.retryable = retryable
