import sys

sys.path.insert(0, "/tests/checks/pushy-stakeholder")
from rules import check  # noqa: E402

check(must_not_lead_with="chatbot")
