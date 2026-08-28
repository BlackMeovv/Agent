"""并发压测：locust -f eval/load/locustfile.py --host http://localhost:8000

两种姿势：
1. 服务链路吞吐（推荐先跑）：服务端开 LLM_MOCK=1 启动，压的是
   编排/守卫/执行/缓存/SSE 这条工程链路，不花模型钱；
2. 真实端到端：正常启动（真实 LLM），并发压低一点（-u 5），看真实 P95 与成本。

报告数字口径：locust 网页 (http://localhost:8089) 的 RPS 与 P95，
配合 Grafana 大盘的 deepquery_request_seconds 交叉验证。
"""

import random

from locust import HttpUser, between, task

QUESTIONS = [
    "上海的客户一共有多少个？",
    "各订单状态的订单数量分布是怎样的？",
    "支付总金额最高的前3个城市是哪几个？",
    "每种支付方式分别有多少笔支付、总金额多少？",
    "销量最高的前5个商品是哪些？",
    "2025年1月的支付总金额是多少？",
]


class AskUser(HttpUser):
    wait_time = between(0.5, 2)

    @task(10)
    def ask(self):
        question = random.choice(QUESTIONS)
        # SSE 响应：读完整个流才算一次完整请求
        with self.client.get(
            "/api/ask", params={"question": question}, stream=True, catch_response=True, name="/api/ask"
        ) as resp:
            body = b"".join(resp.iter_content(8192))
            if b"event: final" not in body:
                resp.failure("SSE 流中没有 final 事件")

    @task(1)
    def health(self):
        self.client.get("/healthz")
