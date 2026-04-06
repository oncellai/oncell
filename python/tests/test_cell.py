"""Tests for the Cell primitive — shell, store, db, search, journal, orchestrator."""

import asyncio
import os
import shutil
import tempfile
import pytest
from oncell import Cell, Step

TEST_DIR = None


@pytest.fixture(autouse=True)
def setup_teardown():
    """Create a temp directory for each test, clean up after."""
    global TEST_DIR
    TEST_DIR = tempfile.mkdtemp(prefix="oncell-test-")
    yield
    shutil.rmtree(TEST_DIR, ignore_errors=True)


def cell() -> Cell:
    return Cell("test-customer", base_dir=TEST_DIR)


# ─── Shell ───

@pytest.mark.asyncio
async def test_shell_echo():
    c = cell()
    result = await c.shell("echo hello")
    assert result.stdout.strip() == "hello"
    assert result.exit_code == 0
    assert not result.failed


@pytest.mark.asyncio
async def test_shell_failure():
    c = cell()
    result = await c.shell("exit 1")
    assert result.exit_code == 1
    assert result.failed


@pytest.mark.asyncio
async def test_shell_stderr():
    c = cell()
    result = await c.shell("echo error >&2")
    assert "error" in result.stderr


@pytest.mark.asyncio
async def test_shell_non_durable():
    c = cell()
    result = await c.shell("echo hi", durable=False)
    assert result.stdout.strip() == "hi"
    assert c.journal.entries == 0  # not journaled


# ─── Store ───

@pytest.mark.asyncio
async def test_store_write_read():
    c = cell()
    await c.store.write("test.txt", "hello world")
    content = await c.store.read("test.txt")
    assert content == "hello world"


@pytest.mark.asyncio
async def test_store_exists():
    c = cell()
    assert not await c.store.exists("nope.txt")
    await c.store.write("yes.txt", "data")
    assert await c.store.exists("yes.txt")


@pytest.mark.asyncio
async def test_store_delete():
    c = cell()
    await c.store.write("del.txt", "bye")
    await c.store.delete("del.txt")
    assert not await c.store.exists("del.txt")


@pytest.mark.asyncio
async def test_store_list():
    c = cell()
    await c.store.write("a.txt", "1")
    await c.store.write("sub/b.txt", "2")
    files = await c.store.list()
    assert "a.txt" in files
    assert os.path.join("sub", "b.txt") in files


@pytest.mark.asyncio
async def test_store_path_traversal():
    c = cell()
    with pytest.raises(ValueError, match="traversal"):
        await c.store.read("../../etc/passwd")


# ─── DB ───

@pytest.mark.asyncio
async def test_db_set_get():
    c = cell()
    await c.db.set("name", "anup")
    assert await c.db.get("name") == "anup"


@pytest.mark.asyncio
async def test_db_get_default():
    c = cell()
    assert await c.db.get("missing") is None
    assert await c.db.get("missing", "fallback") == "fallback"


@pytest.mark.asyncio
async def test_db_json_values():
    c = cell()
    await c.db.set("config", {"theme": "dark", "lang": "ts"})
    val = await c.db.get("config")
    assert val["theme"] == "dark"
    assert val["lang"] == "ts"


@pytest.mark.asyncio
async def test_db_delete():
    c = cell()
    await c.db.set("key", "val")
    await c.db.delete("key")
    assert await c.db.get("key") is None


@pytest.mark.asyncio
async def test_db_keys():
    c = cell()
    await c.db.set("a", 1)
    await c.db.set("b", 2)
    keys = await c.db.keys()
    assert "a" in keys
    assert "b" in keys


@pytest.mark.asyncio
async def test_db_scan():
    c = cell()
    await c.db.set("user:1", {"name": "alice"})
    await c.db.set("user:2", {"name": "bob"})
    await c.db.set("config", "other")
    users = await c.db.scan("user:")
    assert len(users) == 2
    assert "user:1" in users


# ─── Search ───

@pytest.mark.asyncio
async def test_search_index_and_query():
    c = cell()
    # Create some code files
    await c.store.write("src/auth.py", "def authenticate(user, password):\n    return check_password(user, password)")
    await c.store.write("src/main.py", "def main():\n    print('hello world')")

    count = await c.search.index(str(c.work_dir / "src"))
    assert count >= 2

    results = await c.search.query("authenticate password")
    assert len(results) > 0
    assert any("auth" in r["path"] for r in results)


@pytest.mark.asyncio
async def test_search_empty():
    c = cell()
    results = await c.search.query("nothing here")
    assert results == []


@pytest.mark.asyncio
async def test_search_incremental():
    c = cell()
    await c.store.write("src/a.py", "first version")
    count1 = await c.search.index(str(c.work_dir / "src"))

    # Re-index unchanged file — should skip
    count2 = await c.search.index(str(c.work_dir / "src"))
    assert count2 == 0  # no new chunks

    # Change the file — should re-index
    await c.store.write("src/a.py", "second version completely different")
    count3 = await c.search.index(str(c.work_dir / "src"))
    assert count3 > 0


# ─── Journal ───

@pytest.mark.asyncio
async def test_journal_durability():
    """Shell results are journaled. On 'crash' (new Cell), cached results are returned."""
    c = cell()

    # First run — actually executes
    r1 = await c.shell("echo run1")
    assert r1.stdout.strip() == "run1"
    assert c.journal.entries == 1

    # Simulate crash — create new Cell pointing to same directory
    c2 = Cell("test-customer", base_dir=TEST_DIR)

    # Journal should have 1 entry from the previous "run"
    assert c2.journal.entries == 1


@pytest.mark.asyncio
async def test_journal_reset():
    c = cell()
    await c.shell("echo a")
    await c.shell("echo b")
    assert c.journal.entries == 2
    c.journal.reset()
    assert c.journal.entries == 0


# ─── Orchestrator ───

@pytest.mark.asyncio
async def test_orchestrator_run():
    c = cell()
    orch = c.orchestrator("test-task")

    result = await orch.run([
        Step("step1", lambda: c.shell("echo hello")),
        Step("step2", lambda ctx: c.shell(f"echo got {ctx['step1'].stdout.strip()}")),
    ])

    assert result["step1"].stdout.strip() == "hello"
    assert "got hello" in result["step2"].stdout


@pytest.mark.asyncio
async def test_orchestrator_stream():
    c = cell()
    orch = c.orchestrator("stream-task")

    events = []
    async for event in orch.stream([
        Step("s1", lambda: c.shell("echo one")),
        Step("s2", lambda: c.shell("echo two")),
    ]):
        events.append(event)

    statuses = [e.get("status") for e in events]
    assert "starting" in statuses
    assert "done" in statuses


@pytest.mark.asyncio
async def test_orchestrator_failure():
    c = cell()
    orch = c.orchestrator("fail-task")

    async def bad_step():
        raise ValueError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await orch.run([
            Step("good", lambda: c.shell("echo ok")),
            Step("bad", lambda: bad_step()),
        ])


@pytest.mark.asyncio
async def test_orchestrator_spawn():
    c = cell()
    orch = c.orchestrator("spawn-task")

    task_id = await orch.spawn([
        Step("s1", lambda: c.shell("echo async")),
    ])

    assert task_id is not None
    # Give it a moment to complete
    await asyncio.sleep(0.5)
    status = orch.status(task_id)
    assert status is not None
    assert status.status == "done"
