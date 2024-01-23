from ryu.controller import event

class LBEventRoleChange(event.EventBase):
    def __init__(self, dpid, role):
        super(LBEventRoleChange, self).__init__()
        self.dpid = dpid
        self.role = role
