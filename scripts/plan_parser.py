import re
from dataclasses import dataclass, field


@dataclass
class Task:
    number: int
    name: str
    body: str
    depends_on: list = field(default_factory=list)
    produces: list = field(default_factory=list)


_TASK_HEADER_RE = re.compile(r"^### Task (\d+): (.+)$", re.MULTILINE)
_CONSUMES_LINE_RE = re.compile(r"^- Consumes:(.*)$", re.MULTILINE)
_TASK_REF_RE = re.compile(r"\(Task (\d+)\)")
_PRODUCES_RE = re.compile(r"^- Produces:\s*`([^`]+)`", re.MULTILINE)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


def _blank_fenced_code_blocks(text):
    """Replace the contents of fenced code blocks with spaces (keeping
    newlines) so `### Task N:`-shaped text inside example/quoted fences
    isn't mistaken for a real task header, while preserving every other
    character's position so offsets still index correctly into `text`."""
    return _FENCE_RE.sub(
        lambda m: "".join(c if c == "\n" else " " for c in m.group(0)), text,
    )


def parse_plan(text):
    header_text = _blank_fenced_code_blocks(text)
    headers = list(_TASK_HEADER_RE.finditer(header_text))
    tasks = []
    for i, m in enumerate(headers):
        number = int(m.group(1))
        name = m.group(2).strip()
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        body = text[start:end].strip()

        depends_on = set()
        for line_match in _CONSUMES_LINE_RE.finditer(body):
            depends_on.update(int(n) for n in _TASK_REF_RE.findall(line_match.group(1)))

        produces = _PRODUCES_RE.findall(body)

        tasks.append(Task(
            number=number, name=name, body=body,
            depends_on=sorted(depends_on), produces=produces,
        ))

    seen = set()
    for task in tasks:
        if task.number in seen:
            raise ValueError(f"Duplicate task number in plan: Task {task.number}")
        seen.add(task.number)

    return tasks
