"""Pure rule rendering and JSON validation. Does not execute any command."""
import re
from collect_preflight import Stop

PREFIX = "p1lb_"


def table_name(run_id):
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise Stop("INVALID_RUN_ID")
    return PREFIX + run_id


def rules(run_id):
    name = table_name(run_id)
    return ('create table inet ' + name + ' { comment "P1-LB-01:' + run_id + '"; }\n'
            'add set inet ' + name + ' target { type ipv4_addr; flags timeout; timeout 60s; }\n'
            'add element inet ' + name + ' target { 10.1.93.104 timeout 60s }\n'
            'add chain inet ' + name + ' output { type filter hook output priority 0; policy accept; }\n'
            'add rule inet ' + name + ' output oifname "ens160" ip saddr 10.1.93.109 '
            'ip daddr @target tcp dport 6443 counter drop\n').encode("ascii")


def table_rows(data):
    if not isinstance(data, dict) or not isinstance(data.get("nftables"), list):
        raise Stop("INVALID_NFT_TABLE_LIST")
    tables = []
    for obj in data["nftables"]:
        if not isinstance(obj, dict) or set(obj) not in ({"table"}, {"metainfo"}):
            raise Stop("INVALID_NFT_TABLE_LIST_ENTRY")
        if "table" in obj:
            row = obj["table"]
            if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not isinstance(row.get("family"), str):
                raise Stop("INVALID_NFT_TABLE_IDENTITY")
            tables.append(row)
    return tables
