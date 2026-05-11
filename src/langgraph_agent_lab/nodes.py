"""Node skeletons for the LangGraph workflow.

Each function should be small, testable, and return a partial state update. Avoid mutating the
input state in place.
"""

from __future__ import annotations

from .state import AgentState, ApprovalDecision, Route, make_event


def intake_node(state: AgentState) -> dict:
    """Normalize raw query into state fields.

    Added normalization (lowercase, stripping) and metadata logging.
    """
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake: {query[:50]}"],
        "events": [make_event("intake", "completed", "query normalized", length=len(query))],
    }


def classify_node(state: AgentState) -> dict:
    """Classify the query into a route using keyword-based heuristics.

    Priority: risky > tool > missing_info > error > simple.
    """
    query = state.get("query", "").lower()
    words = query.split()
    clean_words = [w.strip("?!.,;:") for w in words]
    
    # Priority 1: Risky
    risky_keywords = {"refund", "delete", "send", "cancel", "remove", "revoke"}
    if any(kw in query for kw in risky_keywords):
        return {
            "route": Route.RISKY.value,
            "risk_level": "high",
            "events": [make_event("classify", "completed", "route=risky")],
        }

    # Priority 2: Tool
    tool_keywords = {"status", "order", "lookup", "check", "track", "find", "search"}
    if any(kw in query for kw in tool_keywords):
        return {
            "route": Route.TOOL.value,
            "risk_level": "low",
            "events": [make_event("classify", "completed", "route=tool")],
        }

    # Priority 3: Missing Info
    # Short query (< 5 words) with "it" as a standalone word
    if len(clean_words) < 5 and "it" in clean_words:
        return {
            "route": Route.MISSING_INFO.value,
            "risk_level": "low",
            "events": [make_event("classify", "completed", "route=missing_info")],
        }

    # Priority 4: Error
    error_keywords = {"timeout", "fail", "error", "crash", "unavailable"}
    if any(kw in query for kw in error_keywords):
        return {
            "route": Route.ERROR.value,
            "risk_level": "low",
            "events": [make_event("classify", "completed", "route=error")],
        }

    # Default: Simple
    return {
        "route": Route.SIMPLE.value,
        "risk_level": "low",
        "events": [make_event("classify", "completed", "route=simple")],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information when query is vague."""
    question = "I'm sorry, I'm not sure what you mean by 'it'. Could you please provide more context or the specific item you're referring to?"
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "missing information requested")],
    }


def tool_node(state: AgentState) -> dict:
    """Call a mock tool.

    Simulates transient failures for error-route scenarios to demonstrate retry loops.
    TODO(student): implement idempotent tool execution and structured tool results.
    """
    attempt = int(state.get("attempt", 0))
    if state.get("route") == Route.ERROR.value and attempt < 2:
        result = f"ERROR: transient failure attempt={attempt} scenario={state.get('scenario_id', 'unknown')}"
    else:
        result = f"mock-tool-result for scenario={state.get('scenario_id', 'unknown')}"
    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", f"tool executed attempt={attempt}")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action for approval."""
    query = state.get("query", "")
    action = f"Executing risky action based on query: '{query}'"
    return {
        "proposed_action": action,
        "events": [make_event("risky_action", "pending_approval", "approval required", action=action)],
    }


def approval_node(state: AgentState) -> dict:
    """Human approval step with optional LangGraph interrupt().

    Set LANGGRAPH_INTERRUPT=true to use real interrupt() for HITL demos.
    Default uses mock decision so tests and CI run offline.

    TODO(student): implement reject/edit decisions and timeout escalation."""
    import os
    from langgraph.types import interrupt

    # If LANGGRAPH_INTERRUPT is true, we use real human-in-the-loop (HITL)
    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        decision_input = interrupt({
            "proposed_action": state.get("proposed_action"),
            "risk_level": state.get("risk_level"),
            "query": state.get("query")
        })
        
        if isinstance(decision_input, dict) and "approved" in decision_input:
            decision = ApprovalDecision(**decision_input)
        else:
            decision = ApprovalDecision(approved=bool(decision_input))
    else:
        # Automated test/CLI mode: mock approval
        decision = ApprovalDecision(approved=True, comment="automated mock approval")
        
    return {
        "approval": decision.model_dump(),
        "events": [make_event("approval", "completed", f"approved={decision.approved}")],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Record a retry attempt or fallback decision.

    TODO(student): implement bounded retry, exponential backoff metadata, and fallback route.
    """
    attempt = int(state.get("attempt", 0)) + 1
    errors = [f"transient failure attempt={attempt}"]
    return {
        "attempt": attempt,
        "errors": errors,
        "events": [make_event("retry", "completed", "retry attempt recorded", attempt=attempt)],
    }


def answer_node(state: AgentState) -> dict:
    """Produce a final response grounded in tool results."""
    tool_results = state.get("tool_results", [])
    if tool_results:
        latest_result = tool_results[-1]
        answer = f"According to our systems: {latest_result}. Is there anything else I can help you with?"
    else:
        answer = "Your request has been processed successfully. How else can I assist you today?"
    
    return {
        "final_answer": answer,
        "events": [make_event("answer", "completed", "answer generated")],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate tool results — the 'done?' check that enables retry loops.

    TODO(student): replace heuristic with LLM-as-judge or structured validation.
    """
    tool_results = state.get("tool_results", [])
    latest = tool_results[-1] if tool_results else ""
    if "ERROR" in latest:
        return {
            "evaluation_result": "needs_retry",
            "events": [make_event("evaluate", "completed", "tool result indicates failure, retry needed")],
        }
    return {
        "evaluation_result": "success",
        "events": [make_event("evaluate", "completed", "tool result satisfactory")],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Log unresolvable failures for manual review.

    Third layer of error strategy: retry -> fallback -> dead letter.
    TODO(student): persist to dead-letter queue, alert on-call, or create support ticket.
    """
    return {
        "final_answer": "Request could not be completed after maximum retry attempts. Logged for manual review.",
        "events": [make_event("dead_letter", "completed", f"max retries exceeded, attempt={state.get('attempt', 0)}")],
    }


def finalize_node(state: AgentState) -> dict:
    """Finalize the run and emit a final audit event."""
    return {"events": [make_event("finalize", "completed", "workflow finished")]}
