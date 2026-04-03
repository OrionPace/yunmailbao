import pandas as pd

data = [
    {"姓名": "欧阳先生(163)", "邮箱": "ouyang2458@163.com"},
    {"姓名": "欧阳先生(gmail)", "邮箱": "oy17352101335@gmail.com"},
    {"姓名": "欧阳先生(sysu)", "邮箱": "ouylx3@mail2.sysu.edu.cn"}
]

df = pd.DataFrame(data)
df.to_excel("test_recipients.xlsx", index=False)
print("test_recipients.xlsx 生成完毕")
