# 参与贡献

行程排程：容量、闭馆日、通勤、预算全在本地算，模型只写解说。

## 本地跑起来

```bash
git clone https://github.com/wushiyi105-jpg/xingji.git && cd xingji
cp .env.example .env      # 填 LLM_API_KEY

python -m xingji import samples/成都景点.txt --destination 成都
python -m xingji plan --destination 成都 --days 3 --weekday 1 --must 大熊猫繁育研究基地,武侯祠
python -m xingji story 1  # 让模型讲一遍（要联网）
python -m xingji serve    # http://127.0.0.1:8776
```

## 跑测试

```bash
python -m unittest discover tests -v
```

单测不依赖真 key：所有模型调用在测试里都换成了假客户端，没配 .env 也能全绿。Windows 终端如果中文乱码，先把环境变量 PYTHONIOENCODING 设成 utf-8。

## 提 PR

1. fork 本仓库，从 main 开一个分支，名字说清要干什么，比如 fix-csv-encoding。
2. 改代码，能顺手补一个测试就补。
3. 本地把上面的测试命令跑一遍，全绿再往下走。
4. 提 PR，写三件事：改了什么、为什么改、本地测试结果。
5. 动到模型调用那一层的，贴一段真实运行输出，比任何描述都省事。

不用写得很正式，说清楚就行。
