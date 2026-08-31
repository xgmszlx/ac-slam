#!/usr/bin/env python3
"""Short Phase 4C-0 map compatibility smoke; never starts exploration."""

import datetime
import hashlib
import json
import shutil
import subprocess
import time
from pathlib import Path

from run_phase2_pairs import (
    AUTHOR_RESULTS, CORE_NODES, ROOT, activated_environment,
    command_output, start_process, stop_process, wait_for_command,
)


MAPS = {
    "map4": {"map_name": "map4/map4", "robot_position": "-17.9 -26.35 0", "map_width": "39.8"},
    "map7": {"map_name": "map7/map7", "robot_position": "-55 -20 0", "map_width": "138.2"},
}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_no_master(env):
    if command_output(["rosparam", "list"], env, timeout=5).returncode == 0:
        raise RuntimeError("a ROS master is already running")


def run_map(name, config, root, env, token):
    output = root / name
    output.mkdir(parents=True, exist_ok=False)
    suffix = "_Phase4C0_smoke_{}_{}".format(name, token)
    tsp_source = AUTHOR_RESULTS / ("tsp_record{}.json".format(suffix))
    prior_source = AUTHOR_RESULTS / ("prior_map{}.pickle".format(suffix))
    roscore = launch = None
    summary = {"map": name, "status": "RUNNING", "exploration_started": False}
    try:
        check_no_master(env)
        roscore = start_process(["roscore"], env, output / "roscore.log")
        wait_for_command(["rosparam", "list"], env, 60, "ROS master")
        command = [
            "roslaunch", "cpp_solver", "exploration.launch",
            "suffix:={}".format(suffix), "strategy:=MyPlanner", "only_use_tsp:=false",
            "tsp_solver:=concorde", "tsp_seed:=21001",
            "map_name:={}".format(config["map_name"]),
            "robot_position:={}".format(config["robot_position"]),
            "map_width:={}".format(config["map_width"]),
            "need_noise:=false", "variance:=0", "enable_loop_diagnostics:=false",
            "loop_diagnostics_path:=", "loop_diagnostics_run_id:=", "oracle_mode:=0",
            "oracle_before:=8", "oracle_after:=8", "oracle_densify_m:=0.5",
            "oracle_span_gate:=4.0", "oracle_repair_max_len:=12.0",
            "oracle_repair_max_wp:=24", "oracle_repair_densify:=0.5", "oracle_dir_lambda:=1.0",
        ]
        (output / "full_command.txt").write_text(subprocess.list2cmdline(command) + "\n")
        launch = start_process(command, env, output / "roslaunch.log")
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline and not tsp_source.is_file():
            if launch.poll() is not None:
                raise RuntimeError("roslaunch exited before TSP generation")
            time.sleep(1)
        if not tsp_source.is_file() or not prior_source.is_file():
            raise RuntimeError("TSP/prior generation timeout")
        shutil.copy2(tsp_source, output / "tsp_record.json")
        shutil.copy2(prior_source, output / "prior_map.pickle")
        services = ("/StartMapping", "/StartExploration", "/prior_graph_service",
                    "/path_plan_service", "/reliable_loop_service")
        for service in services:
            wait_for_command(["rosservice", "type", service], env, 120, service)
        nodes = wait_for_command(["rosnode", "list"], env, 60, "core nodes")
        node_set = set(nodes.splitlines())
        missing = sorted(CORE_NODES - node_set)
        if missing:
            raise RuntimeError("missing core nodes: {}".format(missing))
        (output / "rosnode_list.txt").write_text(nodes)
        (output / "rosservice_list.txt").write_text(
            wait_for_command(["rosservice", "list"], env, 30, "service list")
        )
        start = command_output(["rosservice", "call", "/StartMapping", "{}"], env, timeout=30)
        (output / "start_mapping_service.txt").write_text(start.stdout)
        if start.returncode != 0:
            raise RuntimeError("StartMapping failed")
        map_info = wait_for_command(
            ["rostopic", "echo", "-n", "1", "/map/info"], env, 90, "/map/info"
        )
        (output / "map_info.txt").write_text(map_info)
        saver = command_output([
            "rosrun", "map_server", "map_saver", "-f", str(output / "smoke_map")
        ], env, timeout=120)
        (output / "map_saver.log").write_text(saver.stdout)
        if saver.returncode != 0 or not (output / "smoke_map.yaml").is_file():
            raise RuntimeError("map_saver failed")
        tsp = json.loads((output / "tsp_record.json").read_text())
        summary.update({
            "status": "PASS", "world_launch": "PASS", "robot_spawn": "PASS",
            "prior_load": "PASS", "tsp_generation": "PASS", "map_saving": "PASS",
            "core_nodes": sorted(CORE_NODES), "tsp_solver": tsp.get("solver"),
            "tsp_seed": tsp.get("seed"), "initial_tsp_path": tsp.get("initial_tsp_path"),
            "full_tsp_path": tsp.get("full_tsp_path"),
            "predicted_tsp_length": tsp.get("predicted_tsp_length"),
            "tsp_sha256": sha256(output / "tsp_record.json"),
        })
    except Exception as exc:
        summary.update({"status": "FAIL", "reason": "{}: {}".format(type(exc).__name__, exc)})
        raise
    finally:
        stop_process(launch); stop_process(roscore); time.sleep(2)
        summary["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (output / "smoke_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main():
    env = activated_environment()
    token = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
    root = ROOT / "results" / "phase4c0" / "maps" / ("technical_smoke_" + token)
    root.mkdir(parents=True, exist_ok=False)
    suite = {"status": "RUNNING", "token": token, "formal_performance_run": False, "maps": []}
    try:
        for name, config in MAPS.items():
            suite["maps"].append(run_map(name, config, root, env, token))
        suite["status"] = "PASS"
    except Exception as exc:
        suite.update({"status": "FAIL", "reason": "{}: {}".format(type(exc).__name__, exc)})
        raise
    finally:
        suite["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (root / "smoke_suite.json").write_text(json.dumps(suite, indent=2, sort_keys=True) + "\n")
        print(json.dumps(suite, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
