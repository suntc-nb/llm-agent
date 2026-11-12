from llm_app.core.exceptions import AppError, ConflictError, NotFoundError

err = NotFoundError('会话不存在')
print(err.code, err.http_status, err.log_level, err.message, str(err))

# 验证可以用基类统一捕获
try:
    raise ConflictError('用户名已存在')
except AppError as exc:
    print('被基类捕获:', exc.code, exc.http_status, exc)
