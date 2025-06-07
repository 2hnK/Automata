import platform
from pyjevsim import BehaviorModel, Infinite
import datetime
import math

from pyjevsim.system_message import SysMessage

class CommandControl(BehaviorModel):
    """
    방어 측 지능형 명령통제 시스템
    - 어뢰 행동 패턴 분석 및 적응적 대응
    - 패턴 기반 최적화된 회피 전략
    - 효율적 기만기 배치 시스템
    """
    def __init__(self, name, platform):
        BehaviorModel.__init__(self, name)
        
        self.platform = platform
        
        # 상태 초기화
        self.init_state("Wait")
        self.insert_state("Wait", Infinite)
        self.insert_state("Decision", 0)

        # 포트 설정
        self.insert_input_port("threat_list")
        self.insert_output_port("launch_order")

        self.threat_list = []
        
        # 어뢰 패턴 분석 시스템
        self.torpedo_behavior_pattern = "unknown"     # unknown, distance_priority, movement_tracking
        self.pattern_confidence = 0.0                 # 패턴 신뢰도 (0.0 ~ 1.0)
        self.pattern_history = []                     # 패턴 분석 히스토리
        self.last_torpedo_position = None
        
        # 기만기 배치 관리
        self.decoy_deployed = False
        
        # 거리 기반 탈출 방향 고정 시스템
        self.fixed_escape_angle = None
        self.escape_angle_set = False

    def analyze_torpedo_pattern(self, threat_list):
        """
        어뢰 행동 패턴 분석
        - 거리 우선형 vs 움직임 추적형 식별
        - 패턴 신뢰도 계산
        - 적응적 대응 전략 수립
        """
        if not threat_list:
            return
            
        ship_pos = self.platform.mo.get_position()
        
        # 가장 가까운 어뢰 식별 및 추적
        closest_torpedo = min(threat_list, key=lambda t: 
            math.sqrt((ship_pos[0] - t.get_position()[0])**2 + 
                     (ship_pos[1] - t.get_position()[1])**2))
        
        torpedo_pos = closest_torpedo.get_position()
        
        # 패턴 분석을 위한 데이터 수집
        analysis_data = {
            'torpedo_pos': torpedo_pos,
            'ship_pos': ship_pos,
            'distance': math.sqrt((ship_pos[0] - torpedo_pos[0])**2 + 
                                (ship_pos[1] - torpedo_pos[1])**2)
        }
        
        self.pattern_history.append(analysis_data)
        
        # 최근 4개 데이터로 분석 (메모리 효율성)
        if len(self.pattern_history) > 4:
            self.pattern_history.pop(0)
            
        # 패턴 추론 (최소 3개 데이터 필요)
        if len(self.pattern_history) >= 3:
            self._determine_torpedo_pattern()
            
        self.last_torpedo_position = torpedo_pos

    def _determine_torpedo_pattern(self):
        """
        어뢰 패턴 결정 알고리즘
        - 거리 변화 vs 방향 변화 기반 분석
        - 패턴별 특징 비교 및 신뢰도 계산
        """
        if len(self.pattern_history) < 3:
            return
            
        # 거리 변화 패턴 분석
        distances = [data['distance'] for data in self.pattern_history]
        distance_changes = [distances[i+1] - distances[i] for i in range(len(distances)-1)]
        avg_distance_change = sum(distance_changes) / len(distance_changes)
        
        # 방향 변화 패턴 분석
        positions = [data['torpedo_pos'] for data in self.pattern_history]
        direction_changes = 0
        
        for i in range(2, len(positions)):
            prev_vector = (positions[i-1][0] - positions[i-2][0], 
                          positions[i-1][1] - positions[i-2][1])
            curr_vector = (positions[i][0] - positions[i-1][0], 
                          positions[i][1] - positions[i-1][1])
            
            if prev_vector != (0, 0) and curr_vector != (0, 0):
                # 벡터 간 각도 차이 계산
                try:
                    dot_product = prev_vector[0]*curr_vector[0] + prev_vector[1]*curr_vector[1]
                    mag_prev = math.sqrt(prev_vector[0]**2 + prev_vector[1]**2)
                    mag_curr = math.sqrt(curr_vector[0]**2 + curr_vector[1]**2)
                    
                    cos_angle = dot_product / (mag_prev * mag_curr)
                    cos_angle = max(-1, min(1, cos_angle))  # 수치 안정성
                    angle_diff = math.degrees(math.acos(cos_angle))
                    
                    if angle_diff > 25:  # 25도 이상 방향 변경 감지
                        direction_changes += 1
                except:
                    pass
        
        # 패턴 판단 로직
        if avg_distance_change < -0.5 and direction_changes <= 1:
            # 지속적 접근 + 방향 변화 적음 = 거리 우선형
            if self.torpedo_behavior_pattern != "distance_priority":
                self.torpedo_behavior_pattern = "distance_priority"
                self.pattern_confidence = 0.6  # 즉시 높은 신뢰도 부여
                # 패턴 전환 시 탈출 각도 리셋
                self.escape_angle_set = False
                print(f"🔍 [패턴 분석] 거리 우선형 어뢰 (신뢰도: {self.pattern_confidence:.2f})")
            else:
                self.pattern_confidence = min(self.pattern_confidence + 0.2, 1.0)
                
        elif direction_changes >= 2:
            # 방향 변화 빈번 = 움직임 추적형
            if self.torpedo_behavior_pattern != "movement_tracking":
                self.torpedo_behavior_pattern = "movement_tracking"
                self.pattern_confidence = 0.5  # 중간 신뢰도부터 시작
                # 패턴 전환 시 고정 각도 해제
                self.escape_angle_set = False
                print(f"🔍 [패턴 분석] 움직임 추적형 어뢰 (신뢰도: {self.pattern_confidence:.2f})")
            else:
                self.pattern_confidence = min(self.pattern_confidence + 0.15, 1.0)

    def execute_pattern_based_evasion(self, closest_threat, threat_distance):
        """
        패턴 기반 적응적 회피 전략 실행
        - 거리 우선형: 고정 방향 직선 탈출
        - 움직임 추적형: 변화하는 혼선 유도 기동
        - 패턴 불명: 안전한 기본 회피
        """
        ship_pos = self.platform.mo.get_position()
        threat_pos = closest_threat.get_position()
        
        # 어뢰 접근 방향 계산
        approach_angle = math.degrees(math.atan2(
            threat_pos[0] - ship_pos[0], threat_pos[1] - ship_pos[1]))
        
        if self.torpedo_behavior_pattern == "distance_priority" and self.pattern_confidence > 0.2:
            # 거리 우선형 대응: 고정 방향 직선 탈출
            if not self.escape_angle_set:
                # 첫 번째 탈출 방향 설정 (어뢰 반대 방향)
                self.fixed_escape_angle = (approach_angle + 180) % 360
                self.escape_angle_set = True
                print(f"🚀 [탈출 방향 고정] {self.fixed_escape_angle:.1f}도 - 거리 기반 어뢰 대응")
            
            escape_angle = self.fixed_escape_angle
            strategy = "직선 고정 탈출"
            
        elif self.torpedo_behavior_pattern == "movement_tracking" and self.pattern_confidence > 0.2:
            # 움직임 추적형 대응: 혼선 유도 기동
            current_time = datetime.datetime.now().timestamp()
            
            if threat_distance < 15:
                # 근접 시: 지그재그 기동
                zigzag = int(current_time) % 4
                escape_angle = (approach_angle + 180 + (45 if zigzag < 2 else -45)) % 360
                strategy = "지그재그 기동"
            else:
                # 중거리: 예측 회피 기동
                escape_angle = (approach_angle + 180 + 60) % 360
                strategy = "예측 회피 기동"
                
        else:
            # 패턴 불명 또는 신뢰도 낮음: 안전한 기본 회피
            escape_angle = (approach_angle + 180) % 360
            strategy = "안전 기본 탈출"
            
        print(f"🎯 [{strategy}] {escape_angle:.1f}도 (패턴:{self.torpedo_behavior_pattern}, 신뢰도:{self.pattern_confidence:.1f})")
        return escape_angle

    def should_deploy_decoys(self, threat_distance):
        """
        기만기 배치 판단 로직
        - 배치 거리: 35 이하
        - 중복 배치 방지
        - 효율적 타이밍 제어
        """
        if self.decoy_deployed or threat_distance > 35:
            return False
            
        if threat_distance <= 35:
            self.decoy_deployed = True
            print(f"🎯 [기만기 시스템] 배치 시작 (거리: {threat_distance:.1f})")
            return True
            
        return False

    def ext_trans(self, port, msg):
        """외부 메시지 처리"""
        if port == "threat_list":
            print(f"{self.get_name()}[threat_list]: {datetime.datetime.now()}")
            self.threat_list = msg.retrieve()[0]
            self._cur_state = "Decision"

    def output(self, msg):
        """
        메인 처리 로직
        - 패턴 분석 실행
        - 위협 평가 및 대응
        - 기만기 배치 및 회피 명령 생성
        """
        if not self.threat_list:
            return msg
            
        # 어뢰 패턴 분석
        self.analyze_torpedo_pattern(self.threat_list)
        
        for target in self.threat_list:
            if self.platform.co.threat_evaluation(self.platform.mo, target):
                ship_pos = self.platform.mo.get_position()
                threat_pos = target.get_position()
                threat_distance = math.sqrt((ship_pos[0] - threat_pos[0])**2 + 
                                         (ship_pos[1] - threat_pos[1])**2)
                
                # 기만기 배치 판단
                if self.should_deploy_decoys(threat_distance):
                    launch_message = SysMessage(self.get_name(), "launch_order")
                    launch_message.insert("deploy_decoys")
                    msg.insert_message(launch_message)
                
                # 패턴 기반 회피 전략 실행
                escape_angle = self.execute_pattern_based_evasion(target, threat_distance)
                
                # 회피 명령 생성
                maneuver_message = SysMessage(self.get_name(), "maneuver")
                maneuver_message.insert(escape_angle)
                msg.insert_message(maneuver_message)
                
                break  # 가장 위험한 위협 하나만 처리
        
        return msg

    def int_trans(self):
        """내부 상태 전이"""
        if self._cur_state == "Decision":
            self._cur_state = "Wait"