# 股市脉搏看板

基于 akshare + FastAPI + ECharts 的本地每日复盘看板（深色盘面风，3 屏）。

## 安装
```bash
pip3 install --user -r requirements.txt
```

## 运行
```bash
chmod +x run.sh && ./run.sh
# 浏览器打开 http://127.0.0.1:8000
```

## 测试
```bash
python3 -m pytest -v            # 单元测试（不联网）
python3 -m pytest -m network -v # 联网冒烟
```

## 三屏
- 屏一 市场全局与情绪：外围风向 / A股量能(含放缩量) / 情绪博弈(涨跌停·炸板率·连板·晋级率) / 涨跌分布
- 屏二 资金主线与板块轮动：概念资金流 Top / 申万一级热力图 / 同花顺行业(90)
- 屏三 长线资金：北向资金 / 主力资金 / 融资融券

## 已知限制
- 东财 `clist/get` 批量接口在当前网络被封，改用新浪/同花顺/乐咕/交易所 + 东财 push2ex/datacenter。
- 深交所成交/两融接口异常，相关值可能缺失。
- 无离岸 CNH 稳定源，用中行美元牌价代理。
- 本版为每日快照，不做盘中实时刷新。
