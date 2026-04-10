

# UAV_CFGS: List[Dict[str, Any]]

# IP = "192.168.8.67"
IP = "10.144.1.0"
# IP = "192.168.11.11"
# IP = '10.0.0.157'

UAV_CFGS = [
    # {"id":0,   "tag": "DRONE1",   "ctl": 14540, "grpc": 50051, "ip": "10.144.1.0", "cmd_port": 57000, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
    # {"id":1,   "tag": "DRONE2",   "ctl": 14541, "grpc": 50052, "ip": "10.144.1.0", "cmd_port": 57001, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
    {"id":0,   "tag": "DRONE1",   "ip": "10.144.1.1", "cmd_port": 57000, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
    {"id":1,   "tag": "DRONE2",   "ip": "10.144.1.2", "cmd_port": 57000, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
    {"id":2,   "tag": "DRONE3",   "ctl": 14542, "grpc": 50053, "ip": "10.144.1.0", "cmd_port": 57002, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
    {"id":3,   "tag": "DRONE4",   "ctl": 14543, "grpc": 50054, "ip": "10.144.1.0", "cmd_port": 57003, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
    {"id":4,   "tag": "DRONE5",   "ctl": 14544, "grpc": 50055, "ip": "10.144.1.0", "cmd_port": 57004, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
    {"id":5,   "tag": "DRONE6",   "ctl": 14545, "grpc": 50056, "ip": "10.144.1.0", "cmd_port": 57005, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
    {"id":6,   "tag": "DRONE7",   "ctl": 14546, "grpc": 50057, "ip": "10.144.1.0", "cmd_port": 57006, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
    {"id":7,   "tag": "DRONE8",   "ctl": 14547, "grpc": 50058, "ip": "10.144.1.0", "cmd_port": 57007, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
    {"id":8,   "tag": "DRONE9",   "ctl": 14548, "grpc": 50059, "ip": "10.144.1.0", "cmd_port": 57008, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
    {"id":9,   "tag": "DRONE10",  "ctl": 14549, "grpc": 51060, "ip": "10.144.1.0", "cmd_port": 57009, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
    {"id":10,  "tag": "DRONE11",  "ctl": 14551, "grpc": 51061, "ip": "10.144.1.0", "cmd_port": 57010, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
    {"id":11,  "tag": "DRONE12",  "ctl": 14552, "grpc": 51062, "ip": "10.144.1.0", "cmd_port": 57011, "gui_host": IP, "group": 0, "is_leader": 0, "formation_types":0, "formation_spacing":10},
]
# TCP可能占用50060-50080
# 14550默认QGC通讯
