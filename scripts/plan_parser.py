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


def parse_plan(text):
    headers = list(_TASK_HEADER_RE.finditer(text))
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
    return tasks
