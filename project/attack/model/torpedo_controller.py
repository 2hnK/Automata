import platform
from pyjevsim import BehaviorModel, Infinite
import datetime
import math

from pyjevsim.system_message import SysMessage

class TorpedoCommandControl(BehaviorModel):
    """
    공격 측 지능형 어뢰 제어 시스템
    - 게임 룰 기반 하드 필터링 (속도 2.5~3.5 범위만 허용)
    - 실용적 타겟 선택 알고리즘
    - 집요한 추적 시스템으로 성공률 극대화
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
        self.insert_output_port("target")
        self.threat_list = []
        
        # 실용적 타겟 시스템 설계
        self.current_target_id = None
        self.target_lock_count = 0
        self.min_observation_cycles = 2  # 최소 관찰 사이클 (실용적)
        self.target_history = {}
        self.switch_threshold = 0.15     # 15% 개선 시에만 타겟 변경 (민감한 반응)
        
        # 타겟별 추적 히스토리
        self.target_tracking_history = {}  # {target_id: tracking_count}
        
        # 패턴 분석 데이터
        self.time_step = 0
        self.position_history = {}  # 위치 이력
        self.velocity_history = {}  # 속도 이력
        
        # 확실한 목표 분류
        self.confirmed_ship_targets = set()  # 확인된 수상함
        self.suspected_decoy_targets = set()  # 의심되는 기만기
        
        print("🎯 [지능형 어뢰 시스템] 활성화 - 게임 룰 기반 필터링")

    def update_target_history(self, target):
        """
        타겟 이력 업데이트
        - 위치 및 속도 추적
        - 메모리 효율적 관리
        """
        target_pos = target.get_position()
        target_id = str(target_pos)
        current_time = self.time_step
        
        # 위치 이력 업데이트
        if target_id not in self.position_history:
            self.position_history[target_id] = []
        self.position_history[target_id].append((current_time, target_pos))
        
        # 최근 4개 이력만 유지 (메모리 효율성)
        if len(self.position_history[target_id]) > 4:
            self.position_history[target_id] = self.position_history[target_id][-4:]
        
        # 속도 계산 및 이력 관리
        if len(self.position_history[target_id]) >= 2:
            prev_time, prev_pos = self.position_history[target_id][-2]
            curr_time, curr_pos = self.position_history[target_id][-1]
            
            if curr_time != prev_time:
                velocity = (
                    (curr_pos[0] - prev_pos[0]) / (curr_time - prev_time),
                    (curr_pos[1] - prev_pos[1]) / (curr_time - prev_time)
                )
                
                if target_id not in self.velocity_history:
                    self.velocity_history[target_id] = []
                self.velocity_history[target_id].append((curr_time, velocity))
                
                # 최근 3개 속도 이력만 유지
                if len(self.velocity_history[target_id]) > 3:
                    self.velocity_history[target_id] = self.velocity_history[target_id][-3:]

    def is_valid_ship_target(self, target):
        """
        게임 룰 기반 수상함 필터링
        - 수상함 속도 범위: 2.5~3.5 (게임 룰: 수상함 속도 3.0 고정)
        - 범위 밖의 목표는 명백한 기만기로 판단
        """
        target_pos = target.get_position()
        target_id = str(target_pos)
        
        # 충분한 관찰 데이터가 있는 경우만 필터링 적용
        if (target_id in self.velocity_history and 
            len(self.velocity_history[target_id]) >= 2):
            
            velocities = self.velocity_history[target_id]
            speeds = []
            
            for _, velocity in velocities:
                speed = math.sqrt(velocity[0]**2 + velocity[1]**2)
                speeds.append(speed)
            
            if speeds:
                avg_speed = sum(speeds) / len(speeds)
                
                # 게임 룰 적용: 수상함 속도 3.0 기준
                # 2.5 미만 또는 3.5 초과는 명백한 기만기
                if avg_speed < 2.5 or avg_speed > 3.5:
                    return False  # 기만기로 판단, 필터링
                
        return True  # 유효한 수상함 후보

    def calculate_target_score(self, target):
        """
        실용적 타겟 점수 계산 시스템
        - 거리 점수 (30%): 가까운 목표 우선
        - 기본 수상함 점수 (40%): 필터링 통과한 목표 동일 점수
        - 집요한 추적 점수 (30%): 지속적 추적 보너스
        """
        target_pos = target.get_position()
        target_id = str(target_pos)
        
        # 1. 거리 점수 계산 (30% 가중치)
        torpedo_pos = self.platform.mo.get_position()
        distance = math.sqrt((target_pos[0] - torpedo_pos[0])**2 + 
                           (target_pos[1] - torpedo_pos[1])**2)
        distance_score = max(0, 30 - distance)  # 거리 1당 1점 감소, 최대 30점
        
        # 2. 기본 수상함 점수 (40% 가중치)
        # 하드 필터링을 통과한 모든 타겟에게 동일한 기본 점수
        base_score = 40  # 안정적인 기본 점수
        
        # 3. 집요한 추적 점수 (30% 가중치) - 핵심 차별화 요소
        tracking_count = self.target_tracking_history.get(target_id, 0)
        persistence_score = min(100, 10 + tracking_count * 30)  # 기본 10점 + 추적 보너스
        
        # 가중 평균으로 최종 점수 계산
        total_score = (distance_score * 0.3 + 
                      base_score * 0.4 + 
                      persistence_score * 0.3)
        
        return total_score

    def select_best_target(self, threat_list):
        """
        게임 룰 기반 최적 타겟 선택
        - 1단계: 게임 룰 기반 하드 필터링
        - 2단계: 점수 기반 최적 타겟 선정
        - 3단계: 타겟 스위칭 히스테리시스 적용
        """
        if not threat_list:
            return None
        
        self.time_step += 1
        
        # 1단계: 게임 룰 기반 하드 필터링
        valid_targets = []
        for target in threat_list:
            # 모든 타겟의 이력 업데이트
            self.update_target_history(target)
            
            # 유효한 수상함 후보인지 확인
            if self.is_valid_ship_target(target):
                valid_targets.append(target)
            else:
                # 필터링된 타겟을 의심 기만기로 등록
                target_pos = target.get_position()
                target_id = str(target_pos)
                self.suspected_decoy_targets.add(target_id)
        
        # 안전장치: 유효한 타겟이 없으면 원본 리스트 사용
        if not valid_targets:
            print("⚠️ [필터링] 모든 타겟이 기만기로 판별됨, 원본 리스트 사용")
            valid_targets = threat_list
        else:
            print(f"🎯 [필터링] {len(threat_list)}개 중 {len(valid_targets)}개 타겟이 수상함 후보로 선별")
        
        # 2단계: 유효한 타겟들의 점수 계산
        target_scores = []
        for target in valid_targets:
            score_info = self.calculate_target_score(target)
            target_scores.append({
                'target': target,
                'score_info': score_info
            })
        
        # 점수 순으로 정렬 (내림차순)
        target_scores.sort(key=lambda x: x['score_info'], reverse=True)
        
        # 상위 후보들 디버깅 정보 출력
        print(f"🎯 [타겟 분석] 상위 후보들:")
        for i, ts in enumerate(target_scores[:3]):
            pos = ts['target'].get_position()
            score = ts['score_info']
            target_id = str(pos)
            observation_count = len(self.position_history.get(target_id, []))
            tracking_count = self.target_tracking_history.get(target_id, 0)
            print(f"   {i+1}. 위치({pos[0]:.1f}, {pos[1]:.1f}): "
                  f"총점 {score:.1f} "
                  f"(관찰:{observation_count}회, 추적:{tracking_count}회)")
        
        best_candidate = target_scores[0]
        best_target = best_candidate['target']
        best_score = best_candidate['score_info']
        best_target_id = str(best_target.get_position())
        
        # 3단계: 타겟 스위칭 히스테리시스 적용
        if (self.current_target_id and self.target_lock_count >= 1):
            current_target_score = None
            for ts in target_scores:
                target_id = str(ts['target'].get_position())
                if target_id == self.current_target_id:
                    current_target_score = ts['score_info']
                    break
            
            if current_target_score:
                improvement_ratio = (best_score - current_target_score) / max(current_target_score, 1)
                if improvement_ratio < self.switch_threshold:
                    # 현재 타겟 유지 (히스테리시스)
                    for ts in target_scores:
                        target_id = str(ts['target'].get_position())
                        if target_id == self.current_target_id:
                            # 추적 횟수 증가
                            self.target_tracking_history[target_id] = \
                                self.target_tracking_history.get(target_id, 0) + 1
                            self.target_lock_count += 1
                            print(f"🔒 [타겟 유지] {target_id} (추적:{self.target_tracking_history[target_id]}회)")
                            return ts['target']
        
        # 새로운 타겟 선택
        if best_target_id != self.current_target_id:
            self.current_target_id = best_target_id
            self.target_lock_count = 0
            print(f"🎯 [타겟 변경] {self.current_target_id} (점수: {best_score:.1f})")
        
        # 추적 횟수 증가
        self.target_tracking_history[best_target_id] = \
            self.target_tracking_history.get(best_target_id, 0) + 1
        self.target_lock_count += 1
        
        return best_target

    def ext_trans(self,port, msg):
        if port == "threat_list":
            print(f"🔍 [{self.get_name()}] 위협 목록 수신: {datetime.datetime.now()}")
            self.threat_list = msg.retrieve()[0]
            self._cur_state = "Decision"

    def output(self, msg):
        target = None
        
        if self.threat_list:
            # 실용적 타겟 선택 시스템 사용
            target = self.select_best_target(self.threat_list)
            
            if target:
                # 플랫폼의 기존 타겟 시스템도 활용
                platform_target = self.platform.co.get_target(self.platform.mo, target)
                if platform_target:
                    target = platform_target
                
        # house keeping
        self.threat_list = []
        self.platform.co.reset_target()
        
        if target:
            message = SysMessage(self.get_name(), "target")
            message.insert(target)
            msg.insert_message(message)
        else:
            print("⚠️ [경고] 타겟을 찾지 못했습니다!")
        
        return msg
        
    def int_trans(self):
        if self._cur_state == "Decision":
            self._cur_state = "Wait"