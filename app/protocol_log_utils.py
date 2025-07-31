from pathlib import Path
import json
from typing import List, Dict, Any

PROTOCOL_CHANGE_LOG_FILE = "protocol_change_log.json"

def validate_protocol_log(log_data: List[Dict[str, Any]]) -> bool:
    required_fields = {"cluster_id", "timestamp", "added", "removed", "modified"}
    for entry in log_data:
        if not required_fields.issubset(entry.keys()):
            print(f"Entry missing fields: {entry}")
            return False
        # Additional validation: types
        if not isinstance(entry["cluster_id"], int):
            print(f"Invalid cluster_id type: {entry}")
            return False
        if not isinstance(entry["timestamp"], str):
            print(f"Invalid timestamp type: {entry}")
            return False
        for key in ["added", "removed"]:
            if not isinstance(entry[key], list):
                print(f"Invalid {key} type: {entry}")
                return False
        if not isinstance(entry["modified"], list):
            print(f"Invalid modified type: {entry}")
            return False
    print("Protocol change log validation: PASSED")
    return True

def summarize_protocol_changes(log_data: List[Dict[str, Any]]) -> None:
    cluster_changes = {}
    for entry in log_data:
        cid = entry["cluster_id"]
        cluster_changes.setdefault(cid, {"added": 0, "removed": 0, "modified": 0})
        cluster_changes[cid]["added"] += len(entry.get("added", []))
        cluster_changes[cid]["removed"] += len(entry.get("removed", []))
        cluster_changes[cid]["modified"] += len(entry.get("modified", []))

    print("Protocol Change Summary by Cluster:")
    for cid, changes in sorted(cluster_changes.items()):
        print(f" Cluster {cid}: Added={changes['added']}, Removed={changes['removed']}, Modified={changes['modified']}")

def main():
    try:
        with open(PROTOCOL_CHANGE_LOG_FILE, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"{PROTOCOL_CHANGE_LOG_FILE} not found.")
        return
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return

    if validate_protocol_log(data):
        summarize_protocol_changes(data)

if __name__ == "__main__":
    main()