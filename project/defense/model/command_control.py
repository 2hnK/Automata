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
        """현재 진행방향 기준 최적 회피각: 현재 heading ±45도 범위 내에서 어뢰로부터 가장 멀어지는 방향"""
        if not self.threat_list:
            current_heading = self.platform.mo.heading
            return current_heading
        
        ship_pos = self.platform.mo.get_position()
        current_heading = self.platform.mo.heading
        
        # 가장 가까운 위협 찾기
        closest_threat = min(self.threat_list, 
                           key=lambda t: self.calculate_distance(self.platform.mo, t))
        threat_pos = closest_threat.get_position()
        
        # 위협 방향 계산
        dx = threat_pos[0] - ship_pos[0]
        dy = threat_pos[1] - ship_pos[1]
        threat_angle = math.degrees(math.atan2(dx, dy))
        if threat_angle < 0:
            threat_angle += 360
        
        # 어뢰 속도 및 상태 확인
        threat_speed = self.calculate_speed(closest_threat)
        distance = self.calculate_distance(self.platform.mo, closest_threat)
        
        # 거리 변화량 기반 회피 무력화 판단
        is_distance_increasing = False
        if self.previous_threat_distance is not None:
            distance_change = distance - self.previous_threat_distance
            
            # 거리 증가/감소 누적 판단 (더 관대한 조건)
            if distance_change > 0.2:  # 0.2m 이상 증가
                self.distance_increase_count += 1
            elif distance_change < -0.5:  # 0.5m 이상 감소해야만 리셋
                self.distance_increase_count = max(0, self.distance_increase_count - 1)
            # 미세한 변화(-0.5~0.2)는 카운트 유지
            
            # 3번 연속으로 거리가 증가하거나 절대 거리가 25m 이상이면 회피 성공
            if self.distance_increase_count >= 3 or distance > 25:
                is_distance_increasing = True
        
        # 이전 거리 업데이트
        self.previous_threat_distance = distance
        
        # 어뢰 정지 상태 판단 (더 관대한 조건)
        is_threat_stopped = threat_speed < 2.0  # 속도 2 미만이면 정지로 간주
        is_safe_distance = distance > 100       # 거리 100m 이상이면 안전
        is_far_distance = distance > 300        # 거리 300m 이상이면 원거리
        
        # 회피 성공 상태이거나 정지/원거리 위협이면 현재 방향 유지
        if is_distance_increasing or (is_threat_stopped and is_safe_distance) or is_far_distance:
            reason = ""
            if is_distance_increasing:
                if distance > 25:
                    reason = "안전거리도달"
                else:
                    reason = "회피성공(거리증가)"
                
                # 회피 성공 상태 시작 시간 기록
                if self.escape_success_time is None:
                    self.escape_success_time = datetime.datetime.now()
                    self.last_successful_heading = current_heading
                    
            elif is_threat_stopped and is_safe_distance:
                reason = "정지/안전거리"
            elif is_far_distance:
                reason = "원거리"
            
            print(f"🎯 [직진 유지] {reason} - 현재 방향 유지: {current_heading:.1f}도 (속도:{threat_speed:.1f}, 거리:{distance:.0f}m, 증가횟수:{self.distance_increase_count}, 변화:{distance - self.previous_threat_distance if self.previous_threat_distance else 0:.1f}m)")
            return current_heading
        else:
            # 거리가 증가하지 않으면 회피 성공 상태 리셋
            self.escape_success_time = None
            self.last_successful_heading = None
        
        # 어뢰의 이동 방향 추정 (어뢰 → 수상함 방향)
        ship_pos = self.platform.mo.get_position()
        threat_pos = closest_threat.get_position()
        
        # 어뢰의 이동 방향 (어뢰가 수상함을 향해 오는 방향)
        torpedo_heading = math.degrees(math.atan2(ship_pos[0] - threat_pos[0], ship_pos[1] - threat_pos[1]))
        if torpedo_heading < 0:
            torpedo_heading += 360
        
        # 회피 성공 상태 유지 확인 (최소 10초간 유지)
        if self.escape_success_time is not None:
            success_duration = (datetime.datetime.now() - self.escape_success_time).total_seconds()
            if success_duration < 10.0:  # 10초 미만이면 계속 직진
                print(f"🎯 [성공 상태 유지] 회피 성공 후 직진 유지: {current_heading:.1f}도 (지속시간:{success_duration:.1f}초)")
                return current_heading
        
        # 현재 회피 효과성 확인
        current_escape_effectiveness = self.evaluate_current_escape_effectiveness(closest_threat, current_heading)
        
        # 현재 회피가 효과적이면 유지 (60%로 낮춤 - 더 관대하게)
        if current_escape_effectiveness > 0.6:
            print(f"🎯 [회피 유지] 현재 방향 효과적 - 유지: {current_heading:.1f}도 (효과도:{current_escape_effectiveness:.2f})")
            return current_heading
        
        # 현실적 회피 전략: 어뢰와 비슷한 방향으로 회피 (30-60도 각도)
        ship_speed = abs(self.platform.mo.xy_speed)  # 수상함 속도
        
        # 속도 비율에 따른 회피각 결정
        if threat_speed > ship_speed * 1.5:  # 어뢰가 훨씬 빠름
            # 어뢰와 거의 같은 방향으로 도망 (±20도)
            escape_offset = 20
        elif threat_speed > ship_speed:  # 어뢰가 빠름  
            # 적당한 각도로 회피 (±30도)
            escape_offset = 30
        else:  # 어뢰가 느리거나 비슷함
            # 큰 각도로 회피 가능 (±45도)
            escape_offset = 45
        
        # 급격한 방향 전환 방지 (현재 방향 기준 ±120도 제한)
        max_turn_angle = 120
        
        # 어뢰 진행방향 기준으로 좌우 회피각 계산
        left_escape = (torpedo_heading - escape_offset) % 360
        right_escape = (torpedo_heading + escape_offset) % 360
        
        # 현재 방향 기준 허용 범위
        min_allowed = (current_heading - max_turn_angle) % 360
        max_allowed = (current_heading + max_turn_angle) % 360
        
        # 각도 범위 내 확인 함수
        def is_angle_in_range(angle, min_ang, max_ang):
            if min_ang <= max_ang:
                return min_ang <= angle <= max_ang
            else:  # 0도 경계 넘나드는 경우
                return angle >= min_ang or angle <= max_ang
        
        # 허용 범위 내 회피각 선택
        candidates = []
        if is_angle_in_range(left_escape, min_allowed, max_allowed):
            candidates.append((left_escape, "좌측"))
        if is_angle_in_range(right_escape, min_allowed, max_allowed):
            candidates.append((right_escape, "우측"))
        
        if candidates:
            # 현재 방향과 가장 가까운 회피각 선택
            def angle_diff(a1, a2):
                diff = abs(a1 - a2)
                return min(diff, 360 - diff)
            
            best_angle, best_side = min(candidates, 
                key=lambda x: angle_diff(x[0], current_heading))
            ideal_escape_angle = best_angle
            escape_side = best_side
        else:
            # 허용 범위 내에 적절한 회피각이 없으면 현재 방향 유지
            print(f"🎯 [급회전 방지] 현재 방향 유지: {current_heading:.1f}도 (효과도:{current_escape_effectiveness:.2f})")
            return current_heading
        
        print(f"🎯 [전술 회피] 어뢰방향:{torpedo_heading:.1f}도 → {escape_side} {escape_offset}도 회피:{ideal_escape_angle:.1f}도 (속도비:{threat_speed:.1f}/{ship_speed:.1f}, 효과도:{current_escape_effectiveness:.2f})")
        return ideal_escape_angle
    
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
        """적응형 점진적 회피: 현재 진행방향 기준으로 어뢰로부터 멀어지는 최적 경로"""
        if self.maneuver_start_time is None:
            return
        
        # 추적당하고 있는지 확인
        being_tracked = self.check_being_tracked()
        current_heading = self.platform.mo.heading
        
        if being_tracked:
            # 추적당하고 있으면 최적 탈출각으로 점진적 회피
            target_angle = self.calculate_optimal_escape_angle()
            
            # 현재 방향 유지 조건 확인 (위협 무시 조건과 동일)
            if target_angle == current_heading:
                print(f"🎯 [방향 유지] 위협 무시 상태 - 현재 방향 계속: {current_heading:.1f}도")
                return
            
            # 점진적 방향 전환 (한 번에 최대 20도씩 변경 - 더 빠르게)
            angle_diff = target_angle - current_heading
            
            # 각도 차이를 -180~180 범위로 정규화
            if angle_diff > 180:
                angle_diff -= 360
            elif angle_diff < -180:
                angle_diff += 360
            
            # 점진적 변경 (최대 20도씩으로 증가)
            max_turn_rate = 20
            if abs(angle_diff) > max_turn_rate:
                if angle_diff > 0:
                    new_heading = current_heading + max_turn_rate
                else:
                    new_heading = current_heading - max_turn_rate
            else:
                new_heading = target_angle
            
            # 각도 정규화
            new_heading = new_heading % 360
            
            self.platform.mo.change_heading(new_heading)
            print(f"🚀 [적응 회피] {current_heading:.1f}도 → {new_heading:.1f}도 (목표: {target_angle:.1f}도)")
        else:
            # 추적당하지 않으면 현재 방향 유지 (더 이상 270도로 강제 복귀하지 않음)
            # 단, 극단적인 각도(예: 뒤로 가는 경우)라면 보정
            if 90 <= current_heading <= 180:  # 후진 방향이면
                # 앞쪽 방향으로 점진적 보정
                if current_heading <= 135:
                    new_heading = current_heading - 10  # 더 앞쪽으로
                else:
                    new_heading = current_heading + 10  # 더 앞쪽으로
                
                new_heading = new_heading % 360
                self.platform.mo.change_heading(new_heading)
                print(f"🏃 [방향 보정] {current_heading:.1f}도 → {new_heading:.1f}도 (후진 방지)")





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