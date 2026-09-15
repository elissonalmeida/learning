import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import plan_parser


SAMPLE_PLAN = """
# Sample Implementation Plan

### Task 1: First thing

**Interfaces:**
- Consumes: none
- Produces: `foo.bar(x) -> int`

- [ ] Step 1: do a thing

### Task 2: Second thing

**Interfaces:**
- Consumes: `foo.bar(x) -> int` (Task 1)
- Produces: `foo.baz(y) -> str`

- [ ] Step 1: do another thing

### Task 3: Third thing

**Interfaces:**
- Consumes: `foo.bar(x) -> int` (Task 1), `foo.baz(y) -> str` (Task 2)
- Produces: `foo.qux() -> None`

- [ ] Step 1: do a third thing
"""


def test_parse_plan_extracts_task_numbers_and_names():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    assert [t.number for t in tasks] == [1, 2, 3]
    assert tasks[0].name == "First thing"
    assert tasks[1].name == "Second thing"
    assert tasks[2].name == "Third thing"


def test_parse_plan_task_with_no_task_references_has_no_dependencies():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    assert tasks[0].depends_on == []


def test_parse_plan_extracts_single_dependency():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    assert tasks[1].depends_on == [1]


def test_parse_plan_extracts_multiple_dependencies_from_one_consumes_line():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    assert tasks[2].depends_on == [1, 2]


def test_parse_plan_extracts_produces_signatures():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    assert tasks[0].produces == ["foo.bar(x) -> int"]
    assert tasks[1].produces == ["foo.baz(y) -> str"]
    assert tasks[2].produces == ["foo.qux() -> None"]


def test_parse_plan_includes_full_task_body():
    tasks = plan_parser.parse_plan(SAMPLE_PLAN)
    assert "do a thing" in tasks[0].body
    assert "do another thing" not in tasks[0].body


PLAN_WITH_FENCED_EXAMPLE = """
### Task 1: Real task

**Interfaces:**
- Consumes: none
- Produces: `foo.bar(x) -> int`

Example of how a plan task looks:

```
### Task 1: fake
**Interfaces:**
- Consumes: none
```

- [ ] Step 1: do the real thing
"""


def test_parse_plan_ignores_task_headers_inside_fenced_code_blocks():
    tasks = plan_parser.parse_plan(PLAN_WITH_FENCED_EXAMPLE)
    assert len(tasks) == 1
    assert tasks[0].name == "Real task"
    # The fenced example text is still part of the body (only header
    # matching ignores fences, not body content).
    assert "### Task 1: fake" in tasks[0].body


def test_parse_plan_raises_on_duplicate_task_numbers():
    plan_with_dupes = """
### Task 1: First

- Consumes: none

### Task 1: Duplicate number

- Consumes: none
"""
    with pytest.raises(ValueError):
        plan_parser.parse_plan(plan_with_dupes)
