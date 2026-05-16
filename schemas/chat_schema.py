#使用Pydantic来进行这个数据验证
from pydantic import BaseModel,Field

#1.规定前端必须怎么传数据进来
class ChatRequest(BaseModel):
  #Field(...)表示必填，而且字符串长度不能少于1
  question: str = Field(...,description="用户提出的问题",min_length=1)

#2.规定我们打包返回给前端的数据格式
class ChatResponse(BaseModel):
    answer: str
    status: str="success"
