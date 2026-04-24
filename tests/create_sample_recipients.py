import pandas as pd


data = [
    {"姓名": "张三", "邮箱": "zhangsan@example.com"},
    {"姓名": "李四", "邮箱": "lisi@example.com"},
    {"姓名": "王五", "邮箱": "wangwu@example.com"},
]

df = pd.DataFrame(data)
df.to_excel("tests/fixtures/sample_recipients.xlsx", index=False)
print("tests/fixtures/sample_recipients.xlsx generated")
