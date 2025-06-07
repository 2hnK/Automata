import datetime
import math

from pyjevsim import BehaviorModel, Infinite
from utils.object_db import ObjectDB

from .stationary_decoy import StationaryDecoy
from .self_propelled_decoy import SelfPropelledDecoy
from ..mobject.stationary_decoy_object import StationaryDecoyObject
from ..mobject.self_propelled_decoy_object import SelfPropelledDecoyObject

class Launcher(BehaviorModel):
    """
    공격 측 기만기 발사 시스템
    - 고정식 및 자항식 기만기 발사 관리
    - 비용 제약 내에서 최적 배치
    - 생존시간 기반 자동 소거
    """
    def __init__(self, name, platform):
        BehaviorModel.__init__(self, name)
        
        self.platform = platform
        
        # 상태 초기화
        self.init_state("Wait")
        self.insert_state("Wait", Infinite)
        self.insert_state("Launch", 0)

        # 포트 설정
        self.insert_input_port("order")

    def ext_trans(self, port, msg):
        """외부 발사 명령 처리"""
        if port == "order":
            print(f"🚀 {self.get_name()}[발사명령수신]: {datetime.datetime.now()}")
            self._cur_state = "Launch"

    def output(self, msg):
        """
        기만기 발사 실행
        - 시나리오 설정에 따른 기만기 생성
        - 생존시간 기반 자동 소거 스케줄링
        """
        se = ObjectDB().get_executor()
        
        for idx, decoy in enumerate(self.platform.lo.get_decoy_list()):
            # 생존시간 계산 (올림 처리)
            destroy_t = math.ceil(decoy['lifespan'])
            
            if decoy["type"] == "stationary":
                # 고정식 기만기 생성 (비용: 1.0)
                sdo = StationaryDecoyObject(self.platform.get_position(), decoy)
                decoy_model = StationaryDecoy(f"[Decoy-stationary][{idx}]", sdo)
            elif decoy["type"] == "self_propelled":
                # 자항식 기만기 생성 (비용: 2.5)
                sdo = SelfPropelledDecoyObject(self.platform.get_position(), decoy)
                decoy_model = SelfPropelledDecoy(f"[Decoy-self_propelled][{idx}]", sdo)
            else:
                continue
                
            # 객체 데이터베이스 등록
            ObjectDB().decoys.append((f"[Decoy-{decoy['type']}][{idx}]", sdo))
            ObjectDB().items.append(sdo)
            
            # 시뮬레이션 엔진에 등록 (생존시간 후 자동 소거)
            se.register_entity(decoy_model, 0, destroy_t)
            print(f"  └─ [Decoy-{decoy['type']}][{idx}] 발사완료 (생존시간:{destroy_t})")

        return None

    def int_trans(self):
        """내부 상태 전이"""
        if self._cur_state == "Launch":
            self._cur_state = "Wait"