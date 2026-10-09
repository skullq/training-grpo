import re
from typing import Dict, List, Optional, Union


# 일반적인 Cisco 인터페이스 타입의 축약형 <-> 정규형 매핑 테이블
INTERFACE_PREFIX_MAP = {
    "gi": "GigabitEthernet",
    "gig": "GigabitEthernet",
    "gigabitethernet": "GigabitEthernet",
    "et": "Ethernet",
    "eth": "Ethernet",
    "ethernet": "Ethernet",
    "fa": "FastEthernet",
    "fastethernet": "FastEthernet",
    "te": "TenGigabitEthernet",
    "tengigabitethernet": "TenGigabitEthernet",
    "fo": "FortyGigabitEthernet",
    "fortygigabitethernet": "FortyGigabitEthernet",
    "hu": "HundredGigE",
    "hundredgige": "HundredGigE",
    "po": "Port-Channel",
    "port-channel": "Port-Channel",
    "portchannel": "Port-Channel",
    "vl": "Vlan",
    "vlan": "Vlan",
    "lo": "Loopback",
    "loopback": "Loopback"
}

# 정규형 -> 축약형 매핑
CANONICAL_TO_SHORT = {
    "GigabitEthernet": "Gi",
    "Ethernet": "Et",
    "FastEthernet": "Fa",
    "TenGigabitEthernet": "Te",
    "FortyGigabitEthernet": "Fo",
    "HundredGigE": "Hu",
    "Port-Channel": "Po",
    "Vlan": "Vl",
    "Loopback": "Lo"
}

INTERFACE_REGEX = re.compile(
    r"\b(GigabitEthernet|Ethernet|FastEthernet|TenGigabitEthernet|Port-Channel|Gi|Et|Fa|Te|Po)\s*([0-9]+(?:/[0-9]+)*(?:\.[0-9]+)?)\b",
    re.IGNORECASE
)


def normalize_interface_name(iface: str, short: bool = False) -> str:
    """인터페이스 이름을 표준 정규형(GigabitEthernet0/1) 또는 축약형(Gi0/1)으로 정규화
    
    예시:
    - normalize_interface_name("et0/0") -> "Ethernet0/0"
    - normalize_interface_name("port-channel 0", short=True) -> "Po0"
    - normalize_interface_name("Gi 0/1") -> "GigabitEthernet0/1"
    """
    cleaned = iface.strip()
    match = INTERFACE_REGEX.search(cleaned)
    if not match:
        return cleaned

    prefix_raw = match.group(1).lower()
    port_num = match.group(2)

    canonical_prefix = INTERFACE_PREFIX_MAP.get(prefix_raw, match.group(1))

    if short:
        short_prefix = CANONICAL_TO_SHORT.get(canonical_prefix, canonical_prefix[:2].capitalize())
        return f"{short_prefix}{port_num}"
    return f"{canonical_prefix}{port_num}"


def build_interface_regex_pattern(iface: str) -> str:
    r"""주어진 인터페이스(예: 'Ethernet0/0' 또는 'Et0/0')에 대해
    CLI 출력(축약형/전체형/공백 유무)을 모두 매칭할 수 있는 정규식 패턴 생성
    
    예: 'Ethernet0/0' -> r'(?:Ethernet|Et|eth)\s*0/0'
    """
    match = INTERFACE_REGEX.search(iface.strip())
    if not match:
        return re.escape(iface.strip())

    prefix_raw = match.group(1).lower()
    port_num = re.escape(match.group(2))
    canonical_prefix = INTERFACE_PREFIX_MAP.get(prefix_raw, match.group(1))
    short_prefix = CANONICAL_TO_SHORT.get(canonical_prefix, canonical_prefix[:2])

    prefixes = {canonical_prefix, short_prefix, prefix_raw}
    prefix_pattern = "|".join(re.escape(p) for p in prefixes if p)
    return rf"(?:{prefix_pattern})\s*{port_num}"


def apply_interface_mapping_to_text(text: str, interface_map: Dict[str, str]) -> str:
    """텍스트 내 인터페이스 이름을 사용자 지정 interface_map에 따라 치환
    
    예: interface_map = {"Gi0/1": "Ethernet0/0"} 일 때
    'interface GigabitEthernet0/1' 또는 'Gi0/1'을 'Ethernet0/0'으로 자동 매핑
    """
    if not interface_map or not text:
        return text

    # 매핑 테이블을 표준형 및 축약형 모두에 대해 준비
    normalized_map = {}
    for src_if, dst_if in interface_map.items():
        src_canonical = normalize_interface_name(src_if, short=False)
        src_short = normalize_interface_name(src_if, short=True)
        dst_canonical = normalize_interface_name(dst_if, short=False)
        
        normalized_map[src_canonical.lower()] = dst_canonical
        normalized_map[src_short.lower()] = dst_canonical
        normalized_map[src_if.lower()] = dst_canonical

    def replace_match(m):
        full_match = m.group(0)
        norm = normalize_interface_name(full_match, short=False).lower()
        if norm in normalized_map:
            return normalized_map[norm]
        norm_short = normalize_interface_name(full_match, short=True).lower()
        if norm_short in normalized_map:
            return normalized_map[norm_short]
        if full_match.lower() in normalized_map:
            return normalized_map[full_match.lower()]
        return full_match

    return INTERFACE_REGEX.sub(replace_match, text)


def apply_interface_mapping_to_commands(commands: List[str], interface_map: Dict[str, str]) -> List[str]:
    """명령어 리스트 내 인터페이스 이름 치환"""
    return [apply_interface_mapping_to_text(cmd, interface_map) for cmd in commands]
