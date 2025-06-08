import platform
from pyjevsim import BehaviorModel, Infinite
import datetime
import math
import random
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
        
        # 거리 변화량 추적을 위한 변수들
        self.previous_threat_distance = None  # 이전 프레임 어뢰 거리
        self.distance_increase_count = 0      # 연속적으로 거리가 증가한 횟수
        self.escape_success_time = None       # 회피 성공 시작 시간
        self.last_successful_heading = None   # 마지막 성공한 회피 방향
        
        # 거리 기반 발사 전략 파라미터
        self.distance_thresholds = {
            'far': 1200,    # 원거리 (자항식 기만기)
            'medium': 800,  # 중거리 (자항식 기만기)
            'close': 400    # 근거리 (고정식 기만기)
        }
        
        # 단순 회피 기동 시스템
        self.first_threat_detected = False  # 처음 위협 탐지 여부
        self.evasion_active = False  # 회피 기동 활성화
        self.maneuver_start_time = None  # 기동 시작 시간
        self.current_evasion_heading = 270  # 현재 회피 방향
        self.threat_detection_count = 0  # 연속 위협 탐지 횟수
        self.being_tracked = False  # 추적당하고 있는지 여부
        
        # 안정적 회피 시스템 추가
        self.stable_evasion_heading = None    # 안정적 회피 목표 방향
        self.evasion_direction_locked = False # 회피 방향 고정 여부
        self.last_direction_change_time = None # 마지막 방향 변경 시간
        self.direction_hold_duration = 8.0    # 방향 유지 시간 (초)
        self.consecutive_stable_frames = 0    # 연속 안정 프레임 수
        self.min_stable_frames = 5           # 최소 안정 프레임 수
        self.heading_change_threshold = 5.0   # 방향 변경 임계값 (도)
        self.successful_evasion_heading = None # 성공한 회피 방향
        self.evasion_success_confirmed = False # 회피 성공 확정 여부

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



    def evaluate_threat(self, threat):
        # 거리와 속도 기반 단순 위협 수준 계산
        distance = self.calculate_distance(self.platform.mo, threat)
        speed = self.calculate_speed(threat)
        
        # 거리에 따른 가중치 (가까울수록 위험)
        distance_weight = 1000.0 / max(distance, 1.0)
        
        # 속도에 따른 가중치 (빠를수록 위험)
        speed_weight = 1.0 + (speed / 5.0)
        
        # 단순 위협 수준 계산
        threat_level = distance_weight * speed_weight
        
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

    def calculate_optimal_escape_angle(self):
        """안정적 회피각 계산: 지그재그 현상 방지"""
        if not self.threat_list:
            current_heading = self.platform.mo.heading
            return current_heading
        
        current_time = datetime.datetime.now()
        current_heading = self.platform.mo.heading
        ship_pos = self.platform.mo.get_position()
        
        # 가장 가까운 위협 찾기
        closest_threat = min(self.threat_list, 
                           key=lambda t: self.calculate_distance(self.platform.mo, t))
        threat_pos = closest_threat.get_position()
        distance = self.calculate_distance(self.platform.mo, closest_threat)
        threat_speed = self.calculate_speed(closest_threat)
        
        # 거리 변화량 추적
        is_distance_increasing = False
        distance_change = 0
        if self.previous_threat_distance is not None:
            distance_change = distance - self.previous_threat_distance
            
            # 연속적인 거리 증가 판단
            if distance_change > 0.3:  # 0.3m 이상 증가
                self.distance_increase_count += 1
                self.consecutive_stable_frames += 1
            elif distance_change < -0.3:  # 0.3m 이상 감소
                self.distance_increase_count = max(0, self.distance_increase_count - 2)
                self.consecutive_stable_frames = 0
            else:  # 미세한 변화
                self.consecutive_stable_frames += 1
            
            # 회피 성공 조건: 5번 연속 거리 증가 또는 안전거리 도달
            if self.distance_increase_count >= 5 or distance > 50:
                is_distance_increasing = True
        
        self.previous_threat_distance = distance
        
        # 위협 상태 분석
        is_threat_stopped = threat_speed < 1.5
        is_safe_distance = distance > 150
        is_far_distance = distance > 400
        
        # 회피 성공 확정 및 방향 기억
        if is_distance_increasing and not self.evasion_success_confirmed:
            self.evasion_success_confirmed = True
            self.successful_evasion_heading = current_heading
            self.escape_success_time = current_time
            print(f"✅ [회피 성공] 성공한 방향 기억: {current_heading:.1f}도 (거리:{distance:.0f}m, 변화:{distance_change:.1f}m)")
        
        # 회피 성공 상태에서는 성공한 방향 유지
        if self.evasion_success_confirmed and self.successful_evasion_heading is not None:
            success_duration = (current_time - self.escape_success_time).total_seconds()
            
            # 성공한 방향을 15초간 유지
            if success_duration < 15.0:
                print(f"🎯 [성공 유지] 성공한 회피방향 유지: {self.successful_evasion_heading:.1f}도 (지속:{success_duration:.1f}초)")
                return self.successful_evasion_heading
            else:
                # 15초 후에도 안전하면 회피 성공 상태 해제
                if distance > 100:
                    self.evasion_success_confirmed = False
                    print(f"🏁 [회피 완료] 안전거리 확보, 정상 항해 복귀")
        
        # 안전 상태면 현재 방향 유지
        if (is_threat_stopped and is_safe_distance) or is_far_distance:
            reason = "정지/안전거리" if (is_threat_stopped and is_safe_distance) else "원거리"
            print(f"🎯 [직진 유지] {reason} - 현재 방향: {current_heading:.1f}도")
            return current_heading
        
        # 방향 고정 시간 확인
        direction_locked = False
        if self.last_direction_change_time is not None:
            time_since_change = (current_time - self.last_direction_change_time).total_seconds()
            if time_since_change < self.direction_hold_duration:
                direction_locked = True
        
        # 안정된 회피 방향이 있고 고정 시간 내라면 유지
        if self.stable_evasion_heading is not None and direction_locked:
            # 현재 방향이 목표와 크게 다르지 않으면 유지
            heading_diff = abs(((current_heading - self.stable_evasion_heading + 180) % 360) - 180)
            if heading_diff < 30:  # 30도 이내 차이면 유지
                print(f"🔒 [방향 유지] 안정된 회피방향 유지: {self.stable_evasion_heading:.1f}도 (고정 {time_since_change:.1f}초)")
                return self.stable_evasion_heading
        
        # 새로운 회피 방향 계산
        new_evasion_heading = self.calculate_new_evasion_heading(closest_threat, current_heading)
        
        # 방향 변경이 필요한지 확인
        if self.stable_evasion_heading is None:
            # 처음 회피 방향 설정
            self.stable_evasion_heading = new_evasion_heading
            self.last_direction_change_time = current_time
            print(f"🚀 [새 회피방향] 초기 회피방향 설정: {new_evasion_heading:.1f}도")
        else:
            # 기존 방향과 비교
            heading_diff = abs(((new_evasion_heading - self.stable_evasion_heading + 180) % 360) - 180)
            
            # 큰 차이가 있고 안정 프레임이 충분하면 방향 변경
            if heading_diff > 20 and self.consecutive_stable_frames >= self.min_stable_frames:
                self.stable_evasion_heading = new_evasion_heading
                self.last_direction_change_time = current_time
                self.consecutive_stable_frames = 0
                print(f"🔄 [방향 변경] 새로운 회피방향: {new_evasion_heading:.1f}도 (이전: {current_heading:.1f}도)")
        
        return self.stable_evasion_heading
    
    def calculate_new_evasion_heading(self, threat, current_heading):
        """새로운 회피 방향 계산"""
        ship_pos = self.platform.mo.get_position()
        threat_pos = threat.get_position()
        threat_speed = self.calculate_speed(threat)
        ship_speed = abs(self.platform.mo.xy_speed)
        distance = self.calculate_distance(self.platform.mo, threat)
        
        # 어뢰의 진행 방향 추정
        torpedo_heading = math.degrees(math.atan2(ship_pos[0] - threat_pos[0], ship_pos[1] - threat_pos[1]))
        if torpedo_heading < 0:
            torpedo_heading += 360
        
        # 속도비에 따른 회피 전략
        if threat_speed > ship_speed * 2:
            # 매우 빠른 어뢰: 동일 방향으로 도주 (±15도)
            escape_angle = 15
        elif threat_speed > ship_speed * 1.2:
            # 빠른 어뢰: 약간의 각도로 회피 (±25도)
            escape_angle = 25
        else:
            # 느린 어뢰: 큰 각도로 회피 가능 (±40도)
            escape_angle = 40
        
        # 좌우 회피 방향 계산
        left_escape = (torpedo_heading - escape_angle) % 360
        right_escape = (torpedo_heading + escape_angle) % 360
        
        # 현재 방향과 가까운 쪽 선택 (급격한 방향전환 방지)
        def angle_diff(a1, a2):
            diff = abs(a1 - a2)
            return min(diff, 360 - diff)
        
        left_diff = angle_diff(current_heading, left_escape)
        right_diff = angle_diff(current_heading, right_escape)
        
        # 이전에 성공한 방향이 있다면 우선 고려
        if self.successful_evasion_heading is not None:
            success_left_diff = angle_diff(self.successful_evasion_heading, left_escape)
            success_right_diff = angle_diff(self.successful_evasion_heading, right_escape)
            
            if success_left_diff < success_right_diff:
                chosen_heading = left_escape
                side = "좌측(성공방향)"
            else:
                chosen_heading = right_escape
                side = "우측(성공방향)"
        else:
            # 현재 방향과 가까운 쪽 선택
            if left_diff < right_diff:
                chosen_heading = left_escape
                side = "좌측"
            else:
                chosen_heading = right_escape
                side = "우측"
        
        print(f"🎯 [회피 계산] 어뢰방향:{torpedo_heading:.1f}도 → {side} {escape_angle}도 회피: {chosen_heading:.1f}도 (거리:{distance:.0f}m)")
        return chosen_heading

    def evaluate_current_escape_effectiveness(self, threat, current_heading):
        """현재 회피 방향의 효과성 평가 (0.0~1.0)"""
        if self.previous_threat_distance is None:
            return 0.0
        
        # 거리 변화량 기반 효과성
        distance = self.calculate_distance(self.platform.mo, threat)
        distance_change = distance - self.previous_threat_distance
        
        # 거리 증가율 (1m 증가당 0.1점)
        distance_effectiveness = min(1.0, max(0.0, distance_change * 0.1 + 0.5))
        
        # 현재 방향과 위협 간의 각도 (멀어지는 방향인지)
        ship_pos = self.platform.mo.get_position()
        threat_pos = threat.get_position()
        
        # 위협에서 수상함으로의 벡터 각도
        threat_to_ship_angle = math.degrees(math.atan2(ship_pos[0] - threat_pos[0], ship_pos[1] - threat_pos[1]))
        if threat_to_ship_angle < 0:
            threat_to_ship_angle += 360
        
        # 현재 진행방향과 위협에서 멀어지는 방향의 각도 차이
        angle_diff = abs(((current_heading - threat_to_ship_angle + 180) % 360) - 180)
        
        # 각도 효과성 (정면으로 멀어질수록 높음)
        angle_effectiveness = max(0.0, 1.0 - angle_diff / 180.0)
        
        # 전체 효과성 (거리 변화 70%, 각도 30%)
        total_effectiveness = distance_effectiveness * 0.7 + angle_effectiveness * 0.3
        
        return total_effectiveness



    def check_being_tracked(self):
        """확실하게 추적당하고 있는지 판단"""
        if self.threat_list:
            self.threat_detection_count += 1
            
            # 3번 연속 위협이 탐지되면 추적당한다고 판단
            if self.threat_detection_count >= 3:
                if not self.being_tracked:
                    print("🚨 [추적 확인] 확실하게 추적당하고 있음!")
                    self.being_tracked = True
                return True
        else:
            # 위협이 없으면 카운트 리셋
            if self.threat_detection_count > 0:
                self.threat_detection_count = max(0, self.threat_detection_count - 1)
            
            # 위협이 완전히 사라지면 추적 상태 해제
            if self.threat_detection_count == 0:
                self.being_tracked = False
        
        return self.being_tracked

    def update_intelligent_evasion(self, current_time):
        """안정적이고 부드러운 회피 기동: 지그재그 현상 방지"""
        if self.maneuver_start_time is None:
            return
        
        # 추적당하고 있는지 확인
        being_tracked = self.check_being_tracked()
        current_heading = self.platform.mo.heading
        
        if being_tracked:
            # 추적당하고 있으면 최적 탈출각으로 점진적 회피
            target_angle = self.calculate_optimal_escape_angle()
            
            # 현재 방향과 목표 방향의 차이 계산
            angle_diff = target_angle - current_heading
            
            # 각도 차이를 -180~180 범위로 정규화
            if angle_diff > 180:
                angle_diff -= 360
            elif angle_diff < -180:
                angle_diff += 360
            
            # 목표각에 도달했거나 매우 가까우면 미세 조정
            if abs(angle_diff) <= 2.0:
                # 목표각에 거의 도달 - 현재 방향 유지
                print(f"🎯 [목표 도달] 목표각 도달: {current_heading:.1f}도 ≈ {target_angle:.1f}도")
                return
            elif abs(angle_diff) <= 10.0:
                # 목표각에 가까움 - 매우 부드럽게 조정 (2도씩)
                turn_rate = 2.0
            elif abs(angle_diff) <= 30.0:
                # 중간 거리 - 적당히 조정 (8도씩)
                turn_rate = 8.0
            else:
                # 목표각이 멀음 - 빠르게 조정 (15도씩)
                turn_rate = 15.0
            
            # 방향 전환량 계산
            if abs(angle_diff) > turn_rate:
                if angle_diff > 0:
                    new_heading = current_heading + turn_rate
                else:
                    new_heading = current_heading - turn_rate
            else:
                new_heading = target_angle
            
            # 각도 정규화
            new_heading = new_heading % 360
            
            # 실제 방향 변경이 필요한 경우만 적용
            heading_change = abs(((new_heading - current_heading + 180) % 360) - 180)
            if heading_change >= 1.0:  # 1도 이상 차이날 때만 변경
                self.platform.mo.change_heading(new_heading)
                print(f"🚀 [부드러운 회피] {current_heading:.1f}도 → {new_heading:.1f}도 (목표: {target_angle:.1f}도, 변경량: {heading_change:.1f}도)")
            else:
                print(f"🎯 [안정 유지] 미세 차이로 방향 유지: {current_heading:.1f}도")
                
        else:
            # 추적당하지 않으면 현재 방향 유지하되, 극단적 방향이면 점진적 보정
            if 90 <= current_heading <= 180:  # 후진 방향
                # 전진 방향으로 점진적 보정 (5도씩)
                if current_heading <= 135:
                    new_heading = max(0, current_heading - 5)  # 북쪽 방향으로
                else:
                    new_heading = min(360, current_heading + 5)  # 북쪽 방향으로
                
                new_heading = new_heading % 360
                self.platform.mo.change_heading(new_heading)
                print(f"🏃 [방향 보정] 후진 방지: {current_heading:.1f}도 → {new_heading:.1f}도")





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
            
            # 단순 회피 기동 시작  
            if not self.first_threat_detected:
                # 최초 위협 탐지: 270도 직진 시작
                self.first_threat_detected = True
                self.evasion_active = True
                self.maneuver_start_time = current_time
                
                # 기본 270도 직진
                self.platform.mo.change_heading(270)
                print(f"🚢 [위협 탐지] 270도 직진 시작")
            
            # 회피 기동 업데이트 (추적 확인 후 필요시 회피)
            if self.evasion_active:
                self.update_intelligent_evasion(current_time)
        else:
            # 위협이 없어도 진행 중인 회피 기동 업데이트
            if self.evasion_active and self.maneuver_start_time is not None:
                self.update_intelligent_evasion(current_time)
        
        self.threat_list = []
        return msg
        
    def int_trans(self):
        if self._cur_state == "Decision":
            self._cur_state = "Wait"
            # 발사 중 상태 해제
            self.is_launching = False