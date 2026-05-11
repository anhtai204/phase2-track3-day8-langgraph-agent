import streamlit as st
import json
import sqlite3
import pandas as pd
from pathlib import Path
from typing import Any
from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.state import initial_state, Scenario, Route

# Page config
st.set_page_config(
    page_title="LangGraph Pro Dashboard",
    page_icon="⚡",
    layout="wide"
)

# Custom Styles
st.markdown("""
<style>
    .stApp { background-color: #ffffff; color: #0f172a; }
    .main-card {
        background-color: #f8fafc;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        margin-bottom: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    .stHeader { color: #1e293b; }
</style>
""", unsafe_allow_html=True)

# Helper to get graph
@st.cache_resource
def get_compiled_graph():
    # Use SQLite for persistence to show crash recovery
    checkpointer = build_checkpointer("sqlite", "outputs/checkpoint.db")
    return build_graph(checkpointer=checkpointer)

def main():
    st.title("⚡ LangGraph Agentic Control Center")
    st.markdown("---")
    
    graph = get_compiled_graph()
    
    tabs = st.tabs(["🚀 Live Interactive Demo", "🕰️ Time Travel & History", "📊 Analytics"])
    
    with tabs[0]:
        render_interactive_demo(graph)
        
    with tabs[1]:
        render_time_travel(graph)
        
    with tabs[2]:
        render_analytics()

def render_interactive_demo(graph):
    st.header("Interactive Agent Execution (HITL & Recovery)")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Configuration")
        scenario_query = st.text_area("User Query", "Refund order 12345 and cancel subscription", height=100)
        thread_id = st.text_input("Thread ID (Key for Persistence)", "demo-thread-interactive")
        
        if st.button("🚀 Start / Resume Agent", use_container_width=True):
            st.session_state.running = True
            
    with col2:
        st.subheader("Live Execution Flow")
        
        if "running" in st.session_state and st.session_state.running:
            config = {"configurable": {"thread_id": thread_id}}
            state = graph.get_state(config)
            
            # Initial input or resumed input
            current_input = None
            if not state.values:
                mock_scenario = Scenario(id="interactive", query=scenario_query, expected_route=Route.SIMPLE)
                current_input = initial_state(mock_scenario)
            
            # 1. Handle UI for existing interrupt
            if state.next:
                st.warning(f"⏸️ Agent paused at: **{state.next[0]}**")
                if "approval" in state.next[0]:
                    st.info(f"**Proposed Action:** {state.values.get('proposed_action')}")
                    c_a, c_r = st.columns(2)
                    if c_a.button("✅ Approve Action", use_container_width=True):
                        # Resume by passing the decision back to stream
                        current_input = {"approved": True, "comment": "Approved via UI"}
                    elif c_r.button("❌ Reject", use_container_width=True):
                        current_input = {"approved": False, "comment": "Rejected via UI"}
                    else:
                        return # Wait for button click

            # 2. Execution Loop
            for event in graph.stream(current_input, config=config, stream_mode="values"):
                st.write(f"📍 Node: `{event.get('route', 'START')}`")
                if event.get("final_answer"):
                    st.success(f"**Final Response:** {event['final_answer']}")
                    st.session_state.running = False
                    break
                
                # Check if we just hit a new interrupt during streaming
                new_state = graph.get_state(config)
                if new_state.next:
                    st.rerun()

def render_time_travel(graph):
    st.header("🕰️ Time Travel Explorer")
    thread_id = st.text_input("Enter Thread ID to travel back in time", "demo-thread-interactive")
    
    if thread_id:
        config = {"configurable": {"thread_id": thread_id}}
        history = list(graph.get_state_history(config))
        
        if not history:
            st.info("No history found. Run an interactive demo first.")
            return
            
        st.write(f"Detected **{len(history)}** historical states (checkpoints).")
        
        # Slider to pick state
        selected_idx = st.slider("Select historical point", 0, len(history)-1, 0)
        checkpoint = history[selected_idx]
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown("### Metadata")
            st.write(f"**Step:** {checkpoint.metadata.get('step')}")
            st.write(f"**Node:** `{checkpoint.metadata.get('source', 'START')}`")
            st.write(f"**Time:** {checkpoint.metadata.get('ts')}")
            
        with c2:
            st.markdown("### State Data")
            st.json(checkpoint.values)

def render_analytics():
    st.header("📊 Scenario Metrics")
    metrics_file = Path("outputs/metrics.json")
    if not metrics_file.exists():
        st.error("metrics.json not found. Run `make run-scenarios` first.")
        return
        
    data = json.loads(metrics_file.read_text())
    
    # Summary cards
    c1, c2, c3 = st.columns(3)
    c1.metric("Success Rate", f"{data['success_rate']*100:.1f}%")
    c2.metric("Total Retries", data['total_retries'])
    c3.metric("Total HITL Interrupts", data['total_interrupts'])
    
    st.markdown("---")
    df = pd.DataFrame([
        {
            "Scenario": m['scenario_id'],
            "Status": "✅ Success" if m['success'] else "❌ Failed",
            "Actual Route": m['actual_route'],
            "Retries": m['retry_count'],
            "Interrupts": m['interrupt_count']
        } for m in data['scenario_metrics']
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
