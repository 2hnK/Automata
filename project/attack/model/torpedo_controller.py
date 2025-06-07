import platform
from pyjevsim import BehaviorModel, Infinite
import datetime
import math
import random

from pyjevsim.system_message import SysMessage

class TorpedoCommandControl(BehaviorModel):
    """
    군집 지능 기반 어뢰 시스템
    - 개미 군집 최적화 (ACO) 적용
    - 페로몬 기반 경로 학습
    - 집단 지성으로 최적 목표 탐색
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
        
        # 군집 지능 매개변수
        self.num_ants = 5  # 가상 개미 수
        self.pheromone_map = {}  # 페로몬 지도
        self.evaporation_rate = 0.1  # 증발률
        self.pheromone_strength = 1.0
        
        # 개미별 특성
        self.ant_types = {
            'EXPLORER': {'exploration_factor': 0.8, 'speed': 1.2},
            'HUNTER': {'exploration_factor': 0.3, 'speed': 1.5},
            'ANALYZER': {'exploration_factor': 0.5, 'speed': 1.0},
            'SCOUT': {'exploration_factor': 0.9, 'speed': 0.8},
            'VETERAN': {'exploration_factor': 0.2, 'speed': 1.1}
        }
        
        # 학습 데이터
        self.successful_paths = []
        self.target_success_history = {}
        self.time_step = 0
        
        # 환경 인식
        self.environmental_factors = {
            'threat_density': 0.0,
            'dispersion_index': 0.0,
            'center_of_mass': (0, 0)
        }
        
        print("🐜 [군집 지능 어뢰] 개미 군집 최적화 시스템 활성화")
        print(f"   가상 개미 수: {self.num_ants}, 개미 유형: {list(self.ant_types.keys())}")

    def update_environment_analysis(self, threat_list):
        """환경 분석 업데이트"""
        if not threat_list:
            return
        
        # 위협 밀도 계산
        self.environmental_factors['threat_density'] = len(threat_list)
        
        # 위협 분산도 계산
        positions = [t.get_position() for t in threat_list]
        if len(positions) > 1:
            center_x = sum(pos[0] for pos in positions) / len(positions)
            center_y = sum(pos[1] for pos in positions) / len(positions)
            self.environmental_factors['center_of_mass'] = (center_x, center_y)
            
            # 분산 지수
            distances = [math.sqrt((pos[0] - center_x)**2 + (pos[1] - center_y)**2) 
                        for pos in positions]
            self.environmental_factors['dispersion_index'] = sum(distances) / len(distances)

    def evaporate_pheromones(self):
        """페로몬 증발"""
        for location in list(self.pheromone_map.keys()):
            self.pheromone_map[location] *= (1 - self.evaporation_rate)
            if self.pheromone_map[location] < 0.01:
                del self.pheromone_map[location]

    def deposit_pheromone(self, location, strength):
        """페로몬 증착"""
        location_key = f"{location[0]:.1f},{location[1]:.1f}"
        if location_key not in self.pheromone_map:
            self.pheromone_map[location_key] = 0
        self.pheromone_map[location_key] += strength

    def get_pheromone_level(self, location):
        """특정 위치의 페로몬 농도"""
        location_key = f"{location[0]:.1f},{location[1]:.1f}"
        return self.pheromone_map.get(location_key, 0)

    def ant_evaluate_target(self, ant_type, target, threat_list):
        """개미별 목표 평가"""
        target_pos = target.get_position()
        torpedo_pos = self.platform.mo.get_position()
        
        # 기본 거리 점수
        distance = math.sqrt((target_pos[0] - torpedo_pos[0])**2 + 
                           (target_pos[1] - torpedo_pos[1])**2)
        distance_score = max(0, 100 - distance * 2)
        
        # 페로몬 농도
        pheromone_score = self.get_pheromone_level(target_pos) * 50
        
        # 개미 유형별 특성
        ant_props = self.ant_types[ant_type]
        
        if ant_type == 'EXPLORER':
            # 탐험가: 새로운 지역 선호
            novelty_score = 30 if pheromone_score < 10 else 0
            exploration_bonus = random.uniform(0, 30)
            return distance_score + novelty_score + exploration_bonus
            
        elif ant_type == 'HUNTER':
            # 사냥꾼: 가까운 목표 집중
            if distance < 20:
                return distance_score + 40
            return distance_score
            
        elif ant_type == 'ANALYZER':
            # 분석가: 패턴 기반 평가
            pattern_score = 0
            if len(threat_list) > 1:
                center = self.environmental_factors['center_of_mass']
                center_distance = math.sqrt((target_pos[0] - center[0])**2 + 
                                          (target_pos[1] - center[1])**2)
                if center_distance < 15:
                    pattern_score = 25  # 중심 근처 선호
            return distance_score + pattern_score + pheromone_score
            
        elif ant_type == 'SCOUT':
            # 정찰병: 가장자리 탐색
            if len(threat_list) > 1:
                center = self.environmental_factors['center_of_mass']
                edge_distance = math.sqrt((target_pos[0] - center[0])**2 + 
                                        (target_pos[1] - center[1])**2)
                edge_score = min(30, edge_distance)
                return distance_score + edge_score
            return distance_score + 20
            
        else:  # VETERAN
            # 베테랑: 성공 기록 기반
            success_score = self.target_success_history.get(str(target_pos), 0) * 20
            return distance_score + success_score + pheromone_score

    def swarm_decision_making(self, threat_list):
        """군집 의사결정"""
        if not threat_list:
            return None
        
        ant_evaluations = {}
        
        # 각 개미가 모든 목표를 평가
        for ant_type in self.ant_types:
            ant_evaluations[ant_type] = {}
            for target in threat_list:
                score = self.ant_evaluate_target(ant_type, target, threat_list)
                ant_evaluations[ant_type][target] = score
        
        # 투표 집계 (각 개미의 최고 선택에 가중치)
        target_votes = {}
        voting_details = {}
        
        for ant_type, evaluations in ant_evaluations.items():
            if evaluations:
                # 상위 2개 목표에 투표
                sorted_targets = sorted(evaluations.items(), key=lambda x: x[1], reverse=True)
                
                for i, (target, score) in enumerate(sorted_targets[:2]):
                    target_key = str(target.get_position())
                    vote_weight = (2 - i) * (1 + score / 100)  # 점수에 비례한 가중치
                    
                    if target_key not in target_votes:
                        target_votes[target_key] = 0
                        voting_details[target_key] = []
                    
                    target_votes[target_key] += vote_weight
                    voting_details[target_key].append(f"{ant_type}({vote_weight:.1f})")
        
        # 군집 합의
        if target_votes:
            best_target_key = max(target_votes, key=target_votes.get)
            best_score = target_votes[best_target_key]
            
            # 해당 목표 찾기
            selected_target = None
            for target in threat_list:
                if str(target.get_position()) == best_target_key:
                    selected_target = target
                    break
            
            # 투표 결과 출력
            print(f"🐜 [군집 투표] 선택된 목표: {best_target_key} (총점: {best_score:.1f})")
            for i, (target_key, score) in enumerate(sorted(target_votes.items(), 
                                                         key=lambda x: x[1], reverse=True)[:3]):
                voters = ", ".join(voting_details[target_key])
                print(f"   {i+1}. {target_key}: {score:.1f}점 ({voters})")
            
            return selected_target
        
        return threat_list[0]

    def update_pheromone_trails(self, selected_target):
        """페로몬 경로 업데이트"""
        if not selected_target:
            return
        
        target_pos = selected_target.get_position()
        torpedo_pos = self.platform.mo.get_position()
        
        # 거리 기반 성공도 계산
        distance = math.sqrt((target_pos[0] - torpedo_pos[0])**2 + 
                           (target_pos[1] - torpedo_pos[1])**2)
        success_factor = max(0.1, 1 - distance / 50)
        
        # 페로몬 증착
        pheromone_amount = self.pheromone_strength * success_factor
        self.deposit_pheromone(target_pos, pheromone_amount)
        
        # 성공 기록 업데이트
        target_key = str(target_pos)
        if target_key not in self.target_success_history:
            self.target_success_history[target_key] = 0
        self.target_success_history[target_key] += success_factor * 0.1
        
        print(f"🐜 [페로몬 증착] 위치: {target_pos}, 강도: {pheromone_amount:.2f}")

    def select_best_target(self, threat_list):
        """군집 지능 기반 목표 선택"""
        if not threat_list:
            return None
        
        self.time_step += 1
        
        # 환경 분석
        self.update_environment_analysis(threat_list)
        
        # 페로몬 증발
        self.evaporate_pheromones()
        
        # 군집 의사결정
        selected_target = self.swarm_decision_making(threat_list)
        
        # 페로몬 경로 업데이트
        if selected_target:
            self.update_pheromone_trails(selected_target)
            
            target_pos = selected_target.get_position()
            pheromone_level = self.get_pheromone_level(target_pos)
            print(f"🎯 [군집 선택] 목표: ({target_pos[0]:.1f}, {target_pos[1]:.1f}), "
                  f"페로몬: {pheromone_level:.2f}")
            
            # 주기적 상태 보고
            if self.time_step % 10 == 0:
                print(f"📊 [군집 상태] 페로몬 맵: {len(self.pheromone_map)}개 위치, "
                      f"위협 밀도: {self.environmental_factors['threat_density']}")
        
        return selected_target

    def ext_trans(self, port, msg):
        if port == "threat_list":
            print(f"🔍 [군집 지능] 위협 탐지: {datetime.datetime.now()}")
            self.threat_list = msg.retrieve()[0]
            self._cur_state = "Decision"

    def output(self, msg):
        target = None
        
        if self.threat_list:
            target = self.select_best_target(self.threat_list)
            
            if target:
                # 필수: platform.co.get_target() 사용
                platform_target = self.platform.co.get_target(self.platform.mo, target)
                if platform_target:
                    target = platform_target
        
        # 필수: 초기화
        self.threat_list = []
        self.platform.co.reset_target()
        
        if target:
            message = SysMessage(self.get_name(), "target")
            message.insert(target)
            msg.insert_message(message)
        else:
            print("⚠️ [군집 지능] 목표 선택 실패")
        
        return msg

    def int_trans(self):
        if self._cur_state == "Decision":
            self._cur_state = "Wait"