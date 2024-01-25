import psutil
from ryu.controller import event

class LBEventRoleChange(event.EventBase):
    def __init__(self, dpid, role):
        super(LBEventRoleChange, self).__init__()
        self.dpid = dpid
        self.role = role


def get_cpu_utilization(interval: int = 1) -> int:
    return int(psutil.cpu_percent(interval=interval))


def get_ram_utilization() -> int:
    ram = psutil.virtual_memory()
    return int(ram.percent)
