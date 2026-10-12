# GitHub Actions CI Error Report

**Repository:** `Prince-1005/Pinak-CLI`  
**Commit:** `d4c8d81` (*"fix: resolve code issues, enhance connectivity fallbacks, cleanup repo and optimize tests"*)  
**Workflow Run:** [`38192038293`](https://github.com/Prince-1005/Pinak-CLI/actions/runs/38192038293)  

---

## 1. Summary of Analyzed Jobs

All 8 jobs provided in the request belong to the matrix job **`lint-typecheck-test`** under `.github/workflows/ci.yml`.

| Job ID | Platform | Python Version | Step That Failed | Result | Link |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `114626674897` | `ubuntu-latest` | `3.10` | Pytest with coverage | ❌ Failed | [Job 114626674897](https://github.com/Prince-1005/Pinak-CLI/actions/runs/38192038293/job/114626674897) |
| `114626675046` | `ubuntu-latest` | `3.11` | Pytest with coverage | ❌ Failed | [Job 114626675046](https://github.com/Prince-1005/Pinak-CLI/actions/runs/38192038293/job/114626675046) |
| `114626675048` | `ubuntu-latest` | `3.12` | Pytest with coverage | ❌ Failed | [Job 114626675048](https://github.com/Prince-1005/Pinak-CLI/actions/runs/38192038293/job/114626675048) |
| `114626675056` | `ubuntu-latest` | `3.13` | Pytest with coverage | ❌ Failed | [Job 114626675056](https://github.com/Prince-1005/Pinak-CLI/actions/runs/38192038293/job/114626675056) |
| `114626675079` | `windows-latest` | `3.10` | Pytest with coverage | ❌ Failed | [Job 114626675079](https://github.com/Prince-1005/Pinak-CLI/actions/runs/38192038293/job/114626675079) |
| `114626675171` | `windows-latest` | `3.11` | Pytest with coverage | ❌ Failed | [Job 114626675171](https://github.com/Prince-1005/Pinak-CLI/actions/runs/38192038293/job/114626675171) |
| `114626675039` | `windows-latest` | `3.12` | Pytest with coverage | ❌ Failed | [Job 114626675039](https://github.com/Prince-1005/Pinak-CLI/actions/runs/38192038293/job/114626675039) |
| `114626674947` | `windows-latest` | `3.13` | Pytest with coverage | ❌ Failed | [Job 114626674947](https://github.com/Prince-1005/Pinak-CLI/actions/runs/38192038293/job/114626674947) |

---

## 2. What Succeeded vs. What Failed

In each of the 8 jobs, earlier validation checks **passed completely**:
- ✅ **Ruff Lint** (`ruff check .`) - Passed
- ✅ **Ruff Format Check** (`ruff format --check .`) - Passed
- ✅ **Black Check** (`black --check --line-length=100 .`) - Passed
- ✅ **Mypy Type Check** (`mypy pinak --config-file pyproject.toml`) - Passed

Every job failed strictly at **Step 9: `Pytest with coverage`**:
```bash
pytest --cov=pinak --cov-report=term-missing --cov-fail-under=75
```

---

## 3. The Exact Error

Out of **177 unit tests**, **176 passed** and **1 test failed**:

```text
=================================== FAILURES ===================================
____________ test_handle_download_keyboard_interrupt_during_retry _____________

monkeypatch = <_pytest.monkeypatch.MonkeyPatch object at 0x00000178EE9ABE70>

    def test_handle_download_keyboard_interrupt_during_retry(monkeypatch):
        monkeypatch.setattr(dl_mod, "is_online", lambda timeout=5.0: True)
        monkeypatch.setattr(dl_mod, "get_platform", lambda url: "TestTube")
        monkeypatch.setattr(dl_mod, "url_downloaded_successfully", lambda url: False)
        monkeypatch.setitem(dl_mod.config, "duplicate_action", "ask")
        monkeypatch.setattr(dl_mod, "handle_duplicate", lambda url, interactive=True: "download")
    
        calls = {"n": 0}
    
        def _fail_once(*a, **k):
            calls["n"] += 1
            return {"success": False, "url": "u", "files": [], "errors": ["x"]}
    
        monkeypatch.setattr(dl_mod, "download_instagram_content", _fail_once)
    
        def _ki_wait(seconds):
            raise KeyboardInterrupt()
    
>       monkeypatch.setattr(dl_mod.time, "sleep", _ki_wait)
E       AttributeError: module 'pinak.downloader' has no attribute 'time'

tests/test_engine_flows.py:149: AttributeError
=========================== short test summary info ===========================
FAILED tests/test_engine_flows.py::test_handle_download_keyboard_interrupt_during_retry
1 failed, 176 passed
```

---

## 4. Simple Explanation (Root Cause)

### Why did this happen?
1. In commit `d4c8d81`, `cli/pinak/downloader.py` was refactored.
2. The retry wait logic was changed to use a new helper function called `sleep_with_interrupt(wait)` from `pinak.retry`.
3. Because `time.sleep()` was no longer directly written inside `downloader.py`, the author removed `import time` from the imports at the top of `downloader.py`.
4. However, an existing test inside `cli/tests/test_engine_flows.py` line 149 was still trying to patch `time` on the module:
   ```python
   monkeypatch.setattr(dl_mod.time, "sleep", _ki_wait)
   ```
5. Since `time` is no longer imported inside `dl_mod` (`pinak.downloader`), Python crashed with an `AttributeError: module 'pinak.downloader' has no attribute 'time'`.

### Why did all 8 jobs fail with the same error?
Because this is a unit test code error inside Python itself, not an operating system or Python version specific bug. Therefore, all 4 Python versions (3.10, 3.11, 3.12, 3.13) on both Linux (Ubuntu) and Windows failed in the exact same way.

---

## 5. Applied Fix & Local Verification

**Fix Applied (Recommended Option 1):**  
In [`cli/tests/test_engine_flows.py`](file:///d:/pinak%20Z/cli/tests/test_engine_flows.py), updated `test_handle_download_keyboard_interrupt_during_retry` to patch `dl_mod.sleep_with_interrupt` directly instead of referencing the non-existent `dl_mod.time`:
```python
monkeypatch.setattr(dl_mod, "sleep_with_interrupt", lambda seconds: False)
```

### Verification Results:
- ✅ **Ruff Lint (`ruff check .`):** Passed (0 issues)
- ✅ **Ruff Format (`ruff format --check .`):** Passed (45 files already formatted)
- ✅ **Black Check (`black --check --line-length=100 .`):** Passed (44 files unchanged)
- ✅ **Mypy Type Check (`mypy pinak --config-file pyproject.toml`):** Passed (20 source files verified)
- ✅ **Pytest with Coverage (`pytest --cov=pinak --cov-report=term-missing --cov-fail-under=75`):** **177 passed in 38.4s** (81.39% coverage, requirement ≥ 75%)
