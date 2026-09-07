import argparse
import json
import os
import sys

from wqb_agent.locking import acquire_single_instance_lock, release_single_instance_lock


def load_config(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError) as exc:
        print(f"Config file '{path}' is unreadable or not valid JSON: {exc}")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="WQB Alpha self-evolving research agent"
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config JSON (default: config.json)",
    )
    parser.add_argument(
        "--state-dir",
        default=None,
        help="Directory for memory/trajectory state (overrides config)",
    )
    parser.add_argument(
        "--suggest",
        action="store_true",
        help="LLM-driven phase 1: form hypothesis, discover real fields, "
             "export .wqb_state/suggestions.json (no simulation)",
    )
    parser.add_argument(
        "--run-proposals",
        nargs="?",
        const=".wqb_state/proposals.json",
        default=None,
        metavar="PATH",
        help="LLM-driven phase 2: execute proposals from JSON file "
             "(default .wqb_state/proposals.json) through real simulation",
    )
    parser.add_argument(
        "--factory-run",
        action="store_true",
        help="启动有界 AI Alpha 工厂：恢复优先，持续执行 discovery/模板提案/模拟",
    )
    parser.add_argument(
        "--factory-hours",
        type=float,
        default=None,
        help="AI 工厂运行时长（小时，默认读取 config.agent.factory）",
    )
    parser.add_argument(
        "--factory-stop",
        action="store_true",
        help="请求正在运行的 AI 工厂在安全边界停止（不需要 BRAIN 凭据）",
    )
    parser.add_argument(
        "--factory-status",
        action="store_true",
        help="读取唯一工厂会话状态（不需要 BRAIN 凭据）",
    )
    parser.add_argument(
        "--doctor", action="store_true",
        help="只读检查本地配置、状态和能力，不访问 BRAIN",
    )
    parser.add_argument(
        "--offline", action="store_true",
        help="明确声明只读诊断/审计不访问网络；不能与生产或 smoke 操作混用",
    )
    parser.add_argument(
        "--audit-state", action="store_true",
        help="只读检查本地状态不变量，不访问 BRAIN",
    )
    parser.add_argument(
        "--smoke-readonly", action="store_true",
        help="人工执行的只读平台 smoke 检查；禁止 Simulation/Alpha 写入",
    )
    parser.add_argument(
        "--force-new-round",
        action="store_true",
        help="Explicitly start a new round while preserving an unresolved older checkpoint",
    )
    parser.add_argument(
        "--skip-stale",
        nargs=2,
        metavar=("ROUND", "SIMULATION_ID"),
        help="在至少三次只读 STALE/UNKNOWN 对账后，正式跳过指定远端作业并记录",
    )
    parser.add_argument(
        "--skip-submit-unknown",
        nargs=2,
        metavar=("ROUND", "PROPOSAL_ID"),
        help="用户明确授权后跳过无远端 ID 的 SUBMIT_UNKNOWN，并记录 fingerprint/audit",
    )
    parser.add_argument(
        "--finalize-recorded-round",
        type=int,
        metavar="ROUND",
        help="从 append-only trajectory 收尾已完成但尚未汇总诊断的轮次，不提交 Simulation",
    )
    args = parser.parse_args()

    if args.factory_run and any((
        args.suggest, args.run_proposals, args.skip_stale,
        args.skip_submit_unknown, args.finalize_recorded_round is not None,
        args.factory_stop, args.factory_status,
        args.doctor, args.audit_state, args.smoke_readonly,
    )):
        parser.error("--factory-run 不能与其他研究动作同时使用")
    if args.factory_stop and args.factory_status:
        parser.error("--factory-stop 不能与 --factory-status 同时使用")
    if (args.factory_stop or args.factory_status) and args.factory_hours is not None:
        parser.error("工厂状态/停止动作不能携带 --factory-hours")
    readonly_actions = sum(bool(value) for value in (args.doctor, args.audit_state, args.smoke_readonly))
    if readonly_actions > 1:
        parser.error("--doctor、--audit-state、--smoke-readonly 只能选择一个")
    if args.offline and not (args.doctor or args.audit_state):
        parser.error("--offline 只能与 --doctor 或 --audit-state 一起使用")

    config = None
    # Read-only diagnostics are intentionally runnable on a fresh checkout:
    # they use the checked-in example as a schema-safe fallback, while all
    # production actions still require the user-created config.json.
    if (args.doctor or args.audit_state) and not os.path.exists(args.config):
        example = os.path.join(os.path.dirname(__file__), "config.example.json")
        config = load_config(example)
    else:
        config = load_config(args.config)
    if config is None:
        example = os.path.join(os.path.dirname(__file__), "config.example.json")
        print(
            f"Config file '{args.config}' not found. "
            f"Copy {example} to {args.config} and edit it."
        )
        sys.exit(1)

    if args.state_dir:
        config["agent"]["state_dir"] = args.state_dir

    # Validate once before any client construction.  The legacy mapping is
    # retained for Agent compatibility; typed policy objects are exposed by
    # wqb_agent.config and are not reparsed by read-only commands.
    from wqb_agent.config import parse_config
    try:
        typed_config = parse_config(config)
    except (TypeError, ValueError) as exc:
        print(f"配置无效: {exc}")
        sys.exit(1)

    if args.doctor:
        from wqb_agent.doctor import run_doctor
        print(json.dumps(run_doctor(typed_config, offline=True), ensure_ascii=False, indent=2))
        return
    if args.audit_state:
        from wqb_agent.audit import audit_state
        result = audit_state(config["agent"].get("state_dir", ".wqb_state"))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not result.get("ok"):
            sys.exit(2)
        return
    if args.smoke_readonly:
        from wqb_agent import WQBClient
        from wqb_agent.smoke import run_readonly_smoke
        try:
            client = WQBClient()
            print(json.dumps(run_readonly_smoke(client, config), ensure_ascii=False, indent=2))
        except Exception as exc:
            print(json.dumps({"network_write": False, "status": "UNAVAILABLE", "reason": str(exc)}, ensure_ascii=False, indent=2))
        return

    if args.factory_stop or args.factory_status:
        from wqb_agent.factory_runner import AIFactoryRunner

        state_dir = config["agent"].get("state_dir", ".wqb_state")
        if args.factory_stop:
            session = AIFactoryRunner.request_stop(state_dir)
            if session is None:
                print("未找到可停止的工厂会话")
                return
        else:
            session = AIFactoryRunner.status_view(state_dir)
        if args.factory_stop:
            session = AIFactoryRunner.status_view(state_dir)
        print(json.dumps(session or {"status": "NOT_STARTED"}, ensure_ascii=False, indent=2))
        return

    # Keep read-only factory control commands independent from the production
    # HTTP/client import chain.  This matters on an unattended host where a
    # status/stop operation must work even when credentials or requests are
    # unavailable.
    from wqb_agent import Agent, WQBClient

    try:
        client = WQBClient()
    except Exception as exc:
        print(f"Credentials error: {exc}")
        sys.exit(1)

    agent = Agent(client, typed_config)
    lock_path = None
    try:
        if args.suggest:
            # --suggest 只做字段检索、不模拟，不占模拟实例锁
            agent.run_suggestion_round()
            return
        lock_path = acquire_single_instance_lock(
            config["agent"].get("state_dir", ".wqb_state"),
            operation="factory-run" if args.factory_run else "run-proposals" if args.run_proposals else "skip-stale" if args.skip_stale else "skip-submit-unknown" if args.skip_submit_unknown else "finalize-round" if args.finalize_recorded_round else "idle",
        )
        if lock_path is None:
            sys.exit(1)
        if args.factory_run:
            from wqb_agent.factory_runner import AIFactoryRunner

            factory_cfg = config["agent"].get("factory") or {}
            hours = (
                args.factory_hours
                if args.factory_hours is not None
                else float(factory_cfg.get("max_runtime_sec", 86400)) / 3600
            )
            session = AIFactoryRunner(agent).run(
                duration_sec=max(0.0, hours) * 3600,
                max_rounds=factory_cfg.get("max_rounds", 0),
                idle_sleep_sec=factory_cfg.get("idle_sleep_sec", 30),
                max_simulations=factory_cfg.get("max_simulations", 240),
            )
            print(json.dumps(session, ensure_ascii=False, indent=2))
        elif args.run_proposals:
            agent.run_proposals(
                args.run_proposals,
                allow_unresolved_checkpoint=args.force_new_round,
            )
        elif args.skip_stale:
            agent.skip_stale_reconciled(int(args.skip_stale[0]), args.skip_stale[1])
        elif args.skip_submit_unknown:
            agent.skip_submit_unknown_authorized(int(args.skip_submit_unknown[0]), args.skip_submit_unknown[1])
        elif args.finalize_recorded_round is not None:
            agent.finalize_recorded_round(args.finalize_recorded_round)
        else:
            print(
                "未指定研究动作。请使用：\n"
                "  python main.py --suggest        # 阶段1：假设+真实字段检索\n"
                "  python main.py --run-proposals  # 阶段2：执行通过生产预检的提案\n"
                "  python main.py --factory-run     # 有界一日 AI 工厂"
            )
            sys.exit(1)
    finally:
        release_single_instance_lock(lock_path)


if __name__ == "__main__":
    main()
