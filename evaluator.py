"""Evaluator (critic): judges a worker result against its subtask and returns
a structured verdict. This is the quality gate of the loop."""
from __future__ import annotations

from ..schemas import Evaluation, Task
from ..utils import extract_json
from .base import BaseAgent


class EvaluatorAgent(BaseAgent):
    role = "evaluator"

    def __init__(self, *args, pass_threshold: float = 0.7, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.pass_threshold = pass_threshold

    @property
    def system_prompt(self) -> str:
        return (
            "You are the EVALUATOR (critic). Judge whether the WORKER's result "
            "correctly and completely satisfies the subtask. Be strict but fair. "
            "Check correctness, completeness, edge cases and obvious risks. "
            "Return ONLY JSON: "
            '{"passed": boolean, "score": number between 0 and 1, '
            '"feedback": "specific and actionable"}. '
            "If not passed, feedback MUST state exactly what to fix."
        )

    async def evaluate(self, task: Task, result: str) -> Evaluation:
        user = (
            f"Subtask:\n{task.goal}\n\n"
            f"Worker result:\n{result}\n\n"
            "Evaluate now and return only the JSON verdict."
        )
        resp = await self.call([{"role": "user", "content": user}])
        try:
            data = extract_json(resp.text)
            score = float(data.get("score", 0.0))
            passed = bool(data.get("passed", score >= self.pass_threshold))
            feedback = str(data.get("feedback", ""))
        except Exception:  # noqa: BLE001 - critic returned non-JSON; degrade gracefully
            score, passed, feedback = 0.5, False, resp.text.strip()

        # Enforce the threshold regardless of the model's own 'passed' flag,
        # so the acceptance bar is controlled by config, not the model's mood.
        passed = passed and score >= self.pass_threshold
        return Evaluation(passed=passed, score=score, feedback=feedback, raw=resp.text)
