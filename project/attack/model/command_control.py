import platform
from pyjevsim import BehaviorModel, Infinite, SysMessage
import datetime
import math
import random

class CommandControl(BehaviorModel):
    """
    공격 측 명령통제 시스템
    - 고급 위협 분석 및 실제 수상함 식별
    - 기만기 배치 패턴 감지 및 대응
    - 적응형 전략 선택 시스템
    """
    def __init__(self, name, platform):
        BehaviorModel.__init__(self, name)
        
        self.platform = platform
        
        # 상태 초기화
        self.init_state("Wait")
        self.insert_state("Wait", Infinite)
        self.insert_state("Decision", 0)
        self.insert_state("Detection", 0)

        # 포트 설정
        self.insert_input_port("detection")
        self.insert_output_port("maneuver")
        self.insert_output_port("launcher")
        
        # 위협 분석 시스템
        self.threats = []
        self.threat_history = {}
        self.engagement_strategy = "SMART_SELECTION"  # 지능형 선택 전략
        self.detection_cycle = 0
        self.last_real_ship_position = None
        
        # 기만기 대응 전략
        self.decoy_signatures = {}  # 기만기 식별 데이터
        self.confirmed_decoys = set()  # 확인된 기만기 목록
        self.potential_ship_targets = {}  # 수상함 후보 목록
        
        # 전투 상황 인식
        self.battle_phase = "SEARCH"  # SEARCH(탐색) → ENGAGE(교전) → TERMINAL(종료)
        self.threat_density = 0  # 위협 밀도
        self.decoy_deployment_detected = False  # 기만기 배치 감지 여부
        
        print("🎯 [공격 명령통제] 고급 위협 분석 시스템 활성화")

    def analyze_threat_pattern(self, threats):
        """
        위협 패턴 분석 및 실제 수상함 식별
        - 위협 이동 패턴 추적
        - 기만기 배치 패턴 감지
        - 실제 수상함 위치 추정
        """
        if not threats:
            return
        
        self.detection_cycle += 1
        current_positions = {}
        
        # 현재 탐지된 모든 위협의 위치 기록
        for threat in threats:
            threat_pos = threat.get_position()
            threat_id = str(threat_pos)
            current_positions[threat_id] = threat_pos
            
            # 위협별 이력 관리
            if threat_id not in self.threat_history:
                self.threat_history[threat_id] = {
                    'positions': [],
                    'first_detected': self.detection_cycle,
                    'last_seen': self.detection_cycle,
                    'movement_pattern': [],
                    'suspected_type': 'UNKNOWN',
                    'confidence': 0.5
                }
            
            # 이력 업데이트
            history = self.threat_history[threat_id]
            history['positions'].append((self.detection_cycle, threat_pos))
            history['last_seen'] = self.detection_cycle
            
            # 메모리 효율성을 위해 최근 5개 위치만 유지
            if len(history['positions']) > 5:
                history['positions'] = history['positions'][-5:]
        
        # 기만기 배치 패턴 감지
        self.detect_decoy_deployment(current_positions)
        
        # 개별 위협 분류
        for threat_id, history in self.threat_history.items():
            if len(history['positions']) >= 2:
                self.classify_threat_type(threat_id, history)

    def detect_decoy_deployment(self, current_positions):
        """
        기만기 배치 패턴 감지
        - 동시 출현하는 다수 목표 감지
        - 배치 중심점 계산
        - 실제 수상함 위치 추정
        """
        if len(current_positions) <= 1:
            return
        
        # 새로 출현한 목표들 식별
        new_targets = []
        for threat_id, pos in current_positions.items():
            if threat_id in self.threat_history:
                if self.threat_history[threat_id]['first_detected'] == self.detection_cycle:
                    new_targets.append(pos)
        
        # 동시 다발적 출현은 기만기 배치 신호
        if len(new_targets) >= 3:
            self.decoy_deployment_detected = True
            print(f"🚨 [기만기 배치 감지] {len(new_targets)}개의 새로운 목표 동시 출현")
            
            # 배치 중심점 계산 (기하학적 중심)
            center_x = sum(pos[0] for pos in new_targets) / len(new_targets)
            center_y = sum(pos[1] for pos in new_targets) / len(new_targets)
            
            print(f"🎯 [추정 배치 중심] ({center_x:.1f}, {center_y:.1f})")
            
            # 실제 수상함 위치 추정
            self.estimate_ship_position(center_x, center_y, new_targets)

    def estimate_ship_position(self, center_x, center_y, decoy_positions):
        """
        기만기 배치 패턴 기반 실제 수상함 위치 추정
        - 기만기들의 기하학적 배치 분석
        - 수상함은 보통 배치 중심 근처에 위치
        """
        # 기만기 배치 패턴 분석
        angles = []
        distances = []
        
        for pos in decoy_positions:
            angle = math.atan2(pos[1] - center_y, pos[0] - center_x)
            distance = math.sqrt((pos[0] - center_x)**2 + (pos[1] - center_y)**2)
            angles.append(angle)
            distances.append(distance)
        
        # 실제 수상함은 보통 기만기 배치 중심 근처에 위치할 가능성이 높음
        estimated_ship_pos = (center_x, center_y)
        
        # 현재 위협 목록에서 추정 위치와 가장 가까운 목표를 실제 수상함으로 추정
        min_distance = float('inf')
        best_candidate = None
        
        for threat_id, history in self.threat_history.items():
            if history['positions']:
                current_pos = history['positions'][-1][1]
                dist_to_estimated = math.sqrt(
                    (current_pos[0] - estimated_ship_pos[0])**2 + 
                    (current_pos[1] - estimated_ship_pos[1])**2
                )
                
                if dist_to_estimated < min_distance:
                    min_distance = dist_to_estimated
                    best_candidate = threat_id
        
        # 최적 후보를 실제 수상함으로 지정
        if best_candidate:
            self.threat_history[best_candidate]['suspected_type'] = 'SHIP'
            self.threat_history[best_candidate]['confidence'] = 0.8
            self.last_real_ship_position = self.threat_history[best_candidate]['positions'][-1][1]
            print(f"🎯 [실제 수상함 추정] 위치: {self.last_real_ship_position}")

    def classify_threat_type(self, threat_id, history):
        """
        위협 유형 분류 알고리즘
        - 이동 패턴 분석 (속도, 방향 변화)
        - 게임 룰 기반 분류 (수상함 속도 3.0 고정)
        - 신뢰도 기반 판정
        """
        positions = history['positions']
        
        if len(positions) < 2:
            return
        
        # 이동 벡터 계산
        movements = []
        for i in range(1, len(positions)):
            prev_cycle, prev_pos = positions[i-1]
            curr_cycle, curr_pos = positions[i]
            
            if curr_cycle != prev_cycle:
                movement = (
                    (curr_pos[0] - prev_pos[0]) / (curr_cycle - prev_cycle),
                    (curr_pos[1] - prev_pos[1]) / (curr_cycle - prev_cycle)
                )
                movements.append(movement)
        
        if not movements:
            return
        
        # 속도 분석
        speeds = [math.sqrt(m[0]**2 + m[1]**2) for m in movements]
        avg_speed = sum(speeds) / len(speeds)
        speed_variance = sum((s - avg_speed)**2 for s in speeds) / len(speeds)
        
        # 방향 변화 분석
        direction_changes = []
        for i in range(1, len(movements)):
            prev_angle = math.atan2(movements[i-1][1], movements[i-1][0])
            curr_angle = math.atan2(movements[i][1], movements[i][0])
            angle_change = abs(curr_angle - prev_angle)
            if angle_change > math.pi:
                angle_change = 2 * math.pi - angle_change
            direction_changes.append(angle_change)
        
        avg_direction_change = sum(direction_changes) / len(direction_changes) if direction_changes else 0
        
        # 게임 룰 기반 분류
        confidence = 0.5
        suspected_type = 'UNKNOWN'
        
        # 실제 수상함 특징 (게임 룰: 속도 3.0 고정)
        if (2.5 <= avg_speed <= 3.5 and  # 수상함 표준 속도 범위
            speed_variance < 0.2 and      # 일정한 속도 유지
            avg_direction_change > 0.3):  # 회피기동으로 인한 방향 전환
            suspected_type = 'SHIP'
            confidence = 0.9
            
        # 자항식 기만기 특징
        elif (1.5 <= avg_speed <= 2.5 and  # 낮은 속도
              speed_variance < 0.1 and      # 매우 일정한 속도
              avg_direction_change < 0.2):  # 단순한 직선 이동
            suspected_type = 'SELF_PROPELLED_DECOY'
            confidence = 0.8
            
        # 고정식 기만기 특징
        elif avg_speed < 0.5:  # 거의 정지 상태
            suspected_type = 'STATIONARY_DECOY'
            confidence = 0.9
        
        # 분류 결과 업데이트
        history['suspected_type'] = suspected_type
        history['confidence'] = confidence

    def select_optimal_strategy(self):
        """최적 공격 전략 선택"""
        # 위협 밀도 계산
        active_threats = sum(1 for h in self.threat_history.values() 
                           if self.detection_cycle - h['last_seen'] <= 2)
        self.threat_density = active_threats
        
        # 실제 수상함 후보 수
        ship_candidates = sum(1 for h in self.threat_history.values() 
                            if h['suspected_type'] == 'SHIP' and h['confidence'] > 0.7)
        
        # 확인된 기만기 수
        confirmed_decoys = len(self.confirmed_decoys)
        
        # 전략 결정
        if ship_candidates >= 1:
            self.engagement_strategy = "SMART_SELECTION"
            print("🎯 [전략: 스마트 선택] 실제 수상함 타겟팅")
        elif self.decoy_deployment_detected and confirmed_decoys >= 2:
            self.engagement_strategy = "BYPASS_DECOYS"
            print("🚀 [전략: 기만기 우회] 기만기 무시하고 중심부 공격")
        else:
            self.engagement_strategy = "AGGRESSIVE_HUNT"
            print("⚡ [전략: 적극 수색] 모든 위협 대상 평가")

    def prioritize_threats(self, threats):
        """위협 우선순위 결정"""
        if not threats:
            return []
        
        prioritized = []
        
        for threat in threats:
            threat_pos = threat.get_position()
            threat_id = str(threat_pos)
            
            priority_score = 0
            
            # 기본 거리 점수
            my_pos = self.platform.mo.get_position()
            distance = math.sqrt((my_pos[0] - threat_pos[0])**2 + (my_pos[1] - threat_pos[1])**2)
            distance_score = max(0, 50 - distance)
            
            # 위협 분류 기반 점수
            if threat_id in self.threat_history:
                history = self.threat_history[threat_id]
                
                if history['suspected_type'] == 'SHIP':
                    type_score = 100 * history['confidence']
                elif history['suspected_type'] == 'SELF_PROPELLED_DECOY':
                    type_score = 20 * history['confidence']
                elif history['suspected_type'] == 'STATIONARY_DECOY':
                    type_score = 5 * history['confidence']
                else:
                    type_score = 30  # 미분류 목표
            else:
                type_score = 30  # 새로운 목표
            
            # 전략별 추가 점수
            if self.engagement_strategy == "SMART_SELECTION":
                if threat_id in self.threat_history and self.threat_history[threat_id]['suspected_type'] == 'SHIP':
                    type_score += 50  # 실제 수상함 대폭 가산
                elif threat_id in self.confirmed_decoys:
                    type_score = 1  # 확인된 기만기는 최저 점수
            
            elif self.engagement_strategy == "BYPASS_DECOYS":
                if threat_id in self.confirmed_decoys:
                    type_score = 1  # 기만기 무시
                elif self.last_real_ship_position:
                    # 추정된 실제 수상함 위치 근처 목표 우선
                    dist_to_ship = math.sqrt(
                        (threat_pos[0] - self.last_real_ship_position[0])**2 + 
                        (threat_pos[1] - self.last_real_ship_position[1])**2
                    )
                    if dist_to_ship < 10:
                        type_score += 30
            
            priority_score = distance_score + type_score
            prioritized.append((threat, priority_score, threat_id))
        
        # 점수 순으로 정렬
        prioritized.sort(key=lambda x: x[1], reverse=True)
        
        # 디버깅 정보 출력
        print(f"🎯 [위협 우선순위] 전략: {self.engagement_strategy}")
        for i, (threat, score, tid) in enumerate(prioritized[:3]):
            pos = threat.get_position()
            threat_type = "UNKNOWN"
            if tid in self.threat_history:
                threat_type = self.threat_history[tid]['suspected_type']
            print(f"   {i+1}. 위치({pos[0]:.1f}, {pos[1]:.1f}): 점수 {score:.1f} ({threat_type})")
        
        return [threat for threat, _, _ in prioritized]

    def execute_evasion_maneuver(self, threats):
        """회피 기동 실행"""
        if not threats:
            return None
        
        my_pos = self.platform.mo.get_position()
        
        # 가장 위험한 위협 (가장 가까운 실제 위협) 식별
        most_dangerous = None
        min_danger_distance = float('inf')
        
        for threat in threats:
            threat_pos = threat.get_position()
            threat_id = str(threat_pos)
            distance = math.sqrt((my_pos[0] - threat_pos[0])**2 + (my_pos[1] - threat_pos[1])**2)
            
            # 확인된 기만기는 위험도 낮음
            if threat_id in self.confirmed_decoys:
                continue
                
            if distance < min_danger_distance:
                min_danger_distance = distance
                most_dangerous = threat
        
        if not most_dangerous:
            most_dangerous = threats[0]  # 기본값
        
        # 회피 방향 결정 (기존 로직 사용)
        threat_pos = most_dangerous.get_position()
        approach_angle = math.degrees(math.atan2(
            threat_pos[0] - my_pos[0], threat_pos[1] - my_pos[1]))
        
        # 위협에서 반대 방향으로 회피
        escape_angle = (approach_angle + 180) % 360
        
        # 약간의 무작위성 추가 (예측 어렵게)
        escape_angle += random.uniform(-15, 15)
        escape_angle %= 360
        
        print(f"🏃 [전술 회피] {escape_angle:.1f}도 방향으로 긴급 기동")
        
        return {
            'type': 'evasion',
            'heading': escape_angle,
            'speed_factor': 1.2,  # 약간 속도 증가
            'reason': f'위험 위협 회피 (거리: {min_danger_distance:.1f})'
        }

    def ext_trans(self, port, msg):
        if port == "detection":
            print(f"🔍 [{self.get_name()}] 탐지 정보 수신: {datetime.datetime.now()}")
            threats = msg.retrieve()[0]
            self.threats = threats if threats else []
            
            # 고급 위협 분석 실행
            self.analyze_threat_pattern(self.threats)
            self.select_optimal_strategy()
            
            self._cur_state = "Decision"

    def output(self, msg):
        if self.threats:
            # 위협 우선순위 결정
            prioritized_threats = self.prioritize_threats(self.threats)
            
            # 최고 우선순위 위협을 추적 목표로 설정
            if prioritized_threats:
                # house keeping
                self.threats = []
                
                message = SysMessage(self.get_name(), "launcher")
                message.insert(prioritized_threats)
                msg.insert_message(message)
                
                # 위험한 상황에서는 회피 기동도 고려
                closest_distance = min([
                    math.sqrt((self.platform.mo.get_position()[0] - t.get_position()[0])**2 + 
                             (self.platform.mo.get_position()[1] - t.get_position()[1])**2) 
                    for t in prioritized_threats
                ])
                
                if closest_distance < 15:  # 위험 거리
                    evasion = self.execute_evasion_maneuver(prioritized_threats)
                    if evasion:
                        maneuver_msg = SysMessage(self.get_name(), "maneuver")
                        maneuver_msg.insert(evasion)
                        msg.insert_message(maneuver_msg)
        
        return msg

    def int_trans(self):
        if self._cur_state == "Decision":
            self._cur_state = "Wait"