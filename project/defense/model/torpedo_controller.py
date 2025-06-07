import platform
from pyjevsim import BehaviorModel, Infinite
import datetime
import math

from pyjevsim.system_message import SysMessage

class TorpedoCommandControl(BehaviorModel):
    """
    방어 측 지능형 어뢰 제어 시스템
    - 게임 룰 기반 타겟 분류 (수상함 속도 3.0 고정 활용)
    - 다층 점수 시스템 (거리 + 움직임 + 지속성)
    - 히스테리시스 기반 안정적 타겟 선택
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
        
        # 지능형 타겟 시스템
        self.current_target_id = None
        self.target_lock_count = 0
        self.min_lock_cycles = 3  # 최소 락온 사이클
        self.target_history = []
        self.switch_threshold = 0.1  # 10% 개선 시에만 타겟 변경

    def calculate_target_score(self, target):
        """
        다층 타겟 점수 계산 시스템
        - 거리 점수 (30%): 근접성 우선
        - 움직임 점수 (40%): 게임 룰 기반 수상함 식별
        - 지속성 점수 (30%): 타겟 유지 보너스
        """
        torpedo_pos = self.platform.mo.get_position()
        target_pos = target.get_position()
        
        # 1. 거리 점수 계산 (30% 가중치)
        distance = math.sqrt((torpedo_pos[0] - target_pos[0])**2 + 
                           (torpedo_pos[1] - target_pos[1])**2)
        distance_score = max(0, 30 - distance * 0.5)  # 거리 2당 1점 감소
        
        # 2. 움직임 점수 - 게임 룰 활용 (40% 가중치)
        movement_score = self._calculate_movement_score(target)
        
        # 3. 지속성 점수 - 현재 타겟 유지 보너스 (30% 가중치)
        target_id = str(target_pos)
        persistence_score = 30 if target_id == self.current_target_id else 0
        
        total_score = distance_score + movement_score + persistence_score
        
        return {
            'total': total_score,
            'distance': distance_score,
            'movement': movement_score, 
            'persistence': persistence_score,
            'distance_raw': distance
        }
    
    def _calculate_movement_score(self, target):
        """
        게임 룰 기반 움직임 점수 계산
        - 수상함 속도 3.0 고정 룰 활용
        - 목표 유형별 차별화된 점수 부여
        """
        target_speed = getattr(target, 'xy_speed', 3.0)
        target_type = target.__class__.__name__.lower()
        
        # 게임 룰: 수상함 속도는 3.0으로 고정
        SHIP_STANDARD_SPEED = 3.0
        
        if 'ship' in target_type or 'surface' in target_type:
            # 실제 수상함: 표준 속도에 가까울수록 높은 점수
            speed_deviation = abs(target_speed - SHIP_STANDARD_SPEED)
            if speed_deviation < 0.1:  # 거의 정확한 수상함 속도
                return 40  # 최고 점수
            else:
                return max(0, 40 - speed_deviation * 15)  # 편차에 따라 감점
                
        elif 'decoy' in target_type and 'self_propelled' in target_type:
            # 자항식 기만기: 다양한 속도 패턴으로 위장 시도
            if target_speed == 0:
                return 8  # 정지 상태 (의심스러움)
            elif abs(target_speed - SHIP_STANDARD_SPEED) < 0.5:
                return 25  # 수상함 속도 모방 (중간 위험도)
            else:
                return 20  # 다른 속도 패턴 (의심스러움)
                
        elif 'decoy' in target_type and 'stationary' in target_type:
            # 고정식 기만기: 속도 0으로 명확히 구분
            return 5 if target_speed == 0 else 2
            
        else:
            # 미분류 목표: 속도 기반 기본 점수
            return max(0, 25 - target_speed * 3)
    
    def _calculate_signature_strength(self, target, distance):
        """
        실제 목표 특성 기반 레이더 신호 세기 계산
        - 목표 유형별 RCS (Radar Cross Section) 차이 반영
        - 거리에 따른 신호 감쇠 모델링
        """
        target_type = target.__class__.__name__.lower()
        
        # 목표 유형별 기본 신호 강도
        if 'ship' in target_type or 'surface' in target_type:
            # 수상함: 큰 RCS, 강한 엔진/전자 신호
            base_signature = 25
            
        elif 'decoy' in target_type and 'self_propelled' in target_type:
            # 자항식 기만기: 중간 RCS, 엔진 신호 존재
            base_signature = 15
            
        elif 'decoy' in target_type and 'stationary' in target_type:
            # 고정식 기만기: 작은 RCS, 수동 반사만
            base_signature = 8
            
        else:
            # 미분류 목표: 평균값
            base_signature = 12
        
        # 거리에 따른 신호 감쇠 (현실적 모델)
        distance_factor = max(0.3, 1.0 / (1.0 + distance * 0.1))
        
        # 최종 신호 세기 (0~30점)
        signature_score = min(30, base_signature * distance_factor)
        
        return signature_score

    def select_best_target(self, threat_list):
        """
        최적 타겟 선택 알고리즘
        - 다층 점수 시스템 적용
        - 히스테리시스로 안정성 확보
        - 스마트 타겟 스위칭
        """
        if not threat_list:
            return None
            
        # 모든 타겟의 점수 계산
        target_scores = []
        for target in threat_list:
            score_info = self.calculate_target_score(target)
            target_scores.append({
                'target': target,
                'score_info': score_info
            })
        
        # 점수 순으로 정렬 (내림차순)
        target_scores.sort(key=lambda x: x['score_info']['total'], reverse=True)
        best_candidate = target_scores[0]
        
        # 히스테리시스 적용: 현재 타겟이 락온 상태라면 유지 검토
        if (self.current_target_id and self.target_lock_count >= self.min_lock_cycles):
            current_target_score = None
            for ts in target_scores:
                target_id = str(ts['target'].get_position())
                if target_id == self.current_target_id:
                    current_target_score = ts['score_info']['total']
                    break
            
            if current_target_score:
                # 새로운 타겟이 현재 타겟보다 충분히 좋아야 변경
                improvement_ratio = (best_candidate['score_info']['total'] - current_target_score) / max(current_target_score, 1)
                if improvement_ratio < self.switch_threshold:
                    # 현재 타겟 유지 (히스테리시스 적용)
                    for ts in target_scores:
                        target_id = str(ts['target'].get_position())
                        if target_id == self.current_target_id:
                            return ts['target']
        
        # 새로운 타겟 선택
        new_target = best_candidate['target']
        new_target_id = str(new_target.get_position())
        if new_target_id != self.current_target_id:
            self.current_target_id = new_target_id
            self.target_lock_count = 0
            print(f"🎯 [타겟 변경] {self.current_target_id} (점수: {best_candidate['score_info']['total']:.1f})")
        
        self.target_lock_count += 1
        return new_target

    def ext_trans(self,port, msg):
        """외부 메시지 처리"""
        if port == "threat_list":
            print(f"{self.get_name()}[threat_list]: {datetime.datetime.now()}")
            self.threat_list = msg.retrieve()[0]
            self._cur_state = "Decision"

    def output(self, msg):
        """
        메인 처리 로직
        - 스마트 타겟 선택 시스템 적용
        - 플랫폼 호환성 확보
        - 메시지 생성 및 전송
        """
        target = None
        
        if self.threat_list:
            # 지능형 타겟 선택 시스템 사용
            target = self.select_best_target(self.threat_list)
            
            if target:
                # 플랫폼의 기존 타겟 시스템과 연동
                platform_target = self.platform.co.get_target(self.platform.mo, target)
                if platform_target:
                    target = platform_target
                
        # 리소스 정리
        self.threat_list = []
        self.platform.co.reset_target()
        
        # 타겟 메시지 생성
        if target:
            message = SysMessage(self.get_name(), "target")
            message.insert(target)
            msg.insert_message(message)
        
        return msg
        
    def int_trans(self):
        """내부 상태 전이"""
        if self._cur_state == "Decision":
            self._cur_state = "Wait"