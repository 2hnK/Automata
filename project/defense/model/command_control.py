import platform
from pyjevsim import BehaviorModel, Infinite
import datetime
import math
from pyjevsim.system_message import SysMessage

class CommandControl(BehaviorModel):
    def __init__(self, name, platform):
        print(f"{name}[CommandControl]: {datetime.datetime.now()}")
        BehaviorModel.__init__(self, name)
        
        self.platform = platform
        
        self.init_state("Wait")
        self.insert_state("Wait", Infinite)
        self.insert_state("Decision", 0)

        self.insert_input_port("threat_list")
        self.insert_output_port("launch_order")


        self.threat_list = []
        self.remaining_cost = 10.0  # 총 비용 10
        self.STATIONARY_COST = 1.0
        self.SELF_PROPELLED_COST = 2.5
        self.last_launch_time = None  # 마지막 발사 시간
        self.min_launch_interval = 3.0  # 최소 발사 간격 (초)
        self.critical_distance = 1500  # 위험 거리 (미터)
        self.initial_launch = True  # 초기 발사 여부
        self.launch_count = 0  # 발사 횟수
        self.is_launching = False  # 발사 중 여부
        self.last_threat_id = None  # 마지막 발사한 위협 ID
        self.pending_launch = None  # 대기 중인 발사 정보
        
        # 거리 기반 발사 전략 파라미터
        self.distance_thresholds = {
            'far': 1200,    # 원거리 (자항식 기만기)
            'medium': 800,  # 중거리 (자항식 기만기)
            'close': 400    # 근거리 (고정식 기만기)
        }

    def calculate_distance(self, obj1, obj2):
        # 두 객체 간의 거리 계산
        x1, y1, z1 = obj1.get_position()
        x2, y2, z2 = obj2.get_position()
        return math.sqrt((x2 - x1)**2 + (y2 - y1)**2 + (z2 - z1)**2)

    def calculate_speed(self, obj):
        # 객체 타입에 따른 속도 계산
        if hasattr(obj, 'xy_speed'):
            return abs(obj.xy_speed)
        elif hasattr(obj, 'z_speed'):
            return abs(obj.z_speed)
        return 0.0  # 기본값

    def calculate_heading_diff(self, obj1, obj2):
        # 객체 타입에 따른 방향 차이 계산
        if hasattr(obj1, 'heading') and hasattr(obj2, 'heading'):
            return abs(obj1.heading - obj2.heading)
        return 0.0  # 방향 정보가 없는 경우

    def evaluate_threat(self, threat):
        # 거리, 속도, 방향 등을 고려한 위협 수준 계산
        distance = self.calculate_distance(self.platform.mo, threat)
        speed = self.calculate_speed(threat)
        heading_diff = self.calculate_heading_diff(self.platform.mo, threat)
        
        # 거리에 따른 가중치 (가까울수록 위험)
        distance_weight = 1.0 / max(distance, 1.0)
        
        # 속도에 따른 가중치 (빠를수록 위험)
        speed_weight = 1.0 + (speed / 10.0)  # 속도 기준값 하향 조정
        
        # 방향에 따른 가중치 (정면에서 오는 위협이 더 위험)
        heading_weight = 1.0
        if heading_diff > 0:
            heading_weight = 1.0 + math.cos(math.radians(heading_diff))
        
        # 종합 위협 수준 계산
        threat_level = distance_weight * speed_weight * heading_weight
        
        # 거리가 임계값 이하인 경우 추가 가중치
        if distance < self.critical_distance:
            threat_level *= 1.2  # 가중치 완화
            
        return threat_level

    def select_decoy_type(self, threat_level, distance):
        # 초기 발사 시 자항식 기만기 우선 사용
        if self.initial_launch and self.remaining_cost >= self.SELF_PROPELLED_COST:
            self.initial_launch = False
            return "self_propelled"
        
        # 비용이 부족한 경우
        if self.remaining_cost < self.SELF_PROPELLED_COST:
            return "stationary" if self.remaining_cost >= self.STATIONARY_COST else None
        
        # 거리 기반 기만기 선택
        if distance <= self.distance_thresholds['close']:
            # 근거리에서는 고정식 기만기
            return "stationary"
        elif distance <= self.distance_thresholds['medium']:
            # 중거리에서는 자항식 기만기
            if self.remaining_cost >= self.SELF_PROPELLED_COST:
                return "self_propelled"
            return "stationary"
        elif distance <= self.distance_thresholds['far']:
            # 원거리에서는 자항식 기만기
            if self.remaining_cost >= self.SELF_PROPELLED_COST:
                return "self_propelled"
            return "stationary"
        
        return None

    def ext_trans(self, port, msg):
        if port == "threat_list":
            print(f"{self.get_name()}[threat_list]: {datetime.datetime.now()}")
            self.threat_list = msg.retrieve()[0]
            self._cur_state = "Decision"

    def process_threats(self):
        if not self.threat_list:
            return None

        # 위협 수준에 따라 정렬
        sorted_threats = sorted(
            self.threat_list,
            key=lambda t: self.evaluate_threat(t),
            reverse=True
        )

        # 가장 위험한 위협만 처리
        threat = sorted_threats[0]
        threat_pos = threat.get_position()
        threat_id = f"threat_{threat_pos[0]}_{threat_pos[1]}_{threat_pos[2]}"
        
        # 같은 위협에 대한 연속 발사 방지
        if threat_id == self.last_threat_id:
            return None
        
        distance = self.calculate_distance(self.platform.mo, threat)
        threat_level = self.evaluate_threat(threat)

        if self.platform.co.threat_evaluation(self.platform.mo, threat):
            decoy_type = self.select_decoy_type(threat_level, distance)
            
            if decoy_type:
                cost = self.SELF_PROPELLED_COST if decoy_type == "self_propelled" else self.STATIONARY_COST
                
                if self.remaining_cost >= cost:
                    return {
                        'threat_id': threat_id,
                        'decoy_type': decoy_type,
                        'cost': cost
                    }
        
        return None

    def output(self, msg):
        current_time = datetime.datetime.now()
        
        # 발사 중이면 리턴
        if self.is_launching:
            self.threat_list = []
            return msg

        # 발사 간격 확인
        if self.last_launch_time is not None:
            time_since_last_launch = (current_time - self.last_launch_time).total_seconds()
            if time_since_last_launch < self.min_launch_interval:
                self.threat_list = []
                return msg

        # 위협 처리
        launch_info = self.process_threats()
        
        if launch_info:
            # 발사 중 상태로 설정
            self.is_launching = True
            
            # 기만기 발사 명령
            message = SysMessage(self.get_name(), "launch_order")
            message.retrieve = lambda: [launch_info['decoy_type']]
            msg.insert_message(message)
            
            # 비용 차감 및 발사 시간 기록
            self.remaining_cost -= launch_info['cost']
            self.last_launch_time = current_time
            self.last_threat_id = launch_info['threat_id']
            self.launch_count += 1
            
            # 회피 방향으로 선박 방향 변경
            self.platform.mo.change_heading(self.platform.co.get_evasion_heading())
        
        self.threat_list = []
        return msg
        
    def int_trans(self):
        if self._cur_state == "Decision":
            self._cur_state = "Wait"
            # 발사 중 상태 해제
            self.is_launching = False