import argparse
import asyncio
import json

from mcp.client.session import ClientSession
from mcp.client.sse import sse_client


async def run_demo(
    endpoint: str,
    tool_name: str,
    student_id: str,
    course_code: str,
    final_score: float,
    agent_reasoning: str,
    assessment_id: str | None,
    idempotency_key: str | None,
    auth_token: str | None,
) -> None:
    async with sse_client(endpoint) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Available MCP tools:")
            for tool in tools.tools:
                print(f"- {tool.name}")

            if tool_name == "fetch_real_rubric":
                args = {"course_code": course_code}
                if auth_token:
                    args["auth_token"] = auth_token
                result = await session.call_tool(
                    "fetch_real_rubric",
                    args,
                )
            else:
                args = {
                    "student_id": student_id,
                    "course_code": course_code,
                    "final_score": final_score,
                    "agent_reasoning": agent_reasoning,
                }
                if assessment_id:
                    args["assessment_id"] = assessment_id
                if idempotency_key:
                    args["idempotency_key"] = idempotency_key
                if auth_token:
                    args["auth_token"] = auth_token
                result = await session.call_tool("seal_grade_to_ledger", args)

            print("\nTool response:")
            if hasattr(result, "content"):
                for item in result.content:
                    text = getattr(item, "text", None)
                    if text:
                        try:
                            parsed = json.loads(text)
                            print(json.dumps(parsed, indent=2))
                        except Exception:
                            print(text)
            else:
                print(result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AuraGrade MCP demo client for ledger sealing")
    parser.add_argument("--endpoint", default="http://localhost:8000/mcp/sse", help="MCP SSE endpoint")
    parser.add_argument(
        "--tool",
        default="seal_grade_to_ledger",
        choices=["seal_grade_to_ledger", "fetch_real_rubric"],
        help="Which MCP tool to invoke",
    )
    parser.add_argument("--student-id", default="STU-2026-0142")
    parser.add_argument("--course-code", default="CS401")
    parser.add_argument("--final-score", type=float, default=87.5)
    parser.add_argument(
        "--agent-reasoning",
        default="3-pass loop converged; rubric criteria satisfied.",
    )
    parser.add_argument("--assessment-id", default=None)
    parser.add_argument("--idempotency-key", default=None)
    parser.add_argument("--auth-token", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    cli_args = parse_args()
    asyncio.run(
        run_demo(
            endpoint=cli_args.endpoint,
            tool_name=cli_args.tool,
            student_id=cli_args.student_id,
            course_code=cli_args.course_code,
            final_score=cli_args.final_score,
            agent_reasoning=cli_args.agent_reasoning,
            assessment_id=cli_args.assessment_id,
            idempotency_key=cli_args.idempotency_key,
            auth_token=cli_args.auth_token,
        )
    )
