# Testing Guidelines

## Testing rule for PySide6-dependent tests

If a test imports any symbol from PySide6 (QtWidgets, QtCore, QtGui, etc.), it must include a guard that skips the test when PySide6 is unavailable.

1. **Add a `pytest.importorskip("PySide6")` guard at the top of the test file:**

    ```python
    import pytest
    pytest.importorskip("PySide6", reason="UI tests require PySide6")
    ```

2. **Ensure the test is skipped when PySide6 is not installed.**
3. **Use mocks for pure logic tests.** Tests that do not require a real Qt runtime should use mocks instead of real PySide6 imports.

### Optional mock fallback example

If you need to keep module imports working without PySide6 for logic-only tests, use a lightweight mock in `tests/conftest.py`:

```python
import sys
from types import ModuleType

try:
    import PySide6  # real import on local dev with PySide6 installed
except ImportError:
    mock = ModuleType("PySide6")
    qtwidgets = ModuleType("PySide6.QtWidgets")
    mock.QtWidgets = qtwidgets
    sys.modules["PySide6"] = mock
    sys.modules["PySide6.QtWidgets"] = qtwidgets
```
