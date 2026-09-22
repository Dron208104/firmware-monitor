from .db import Base, SessionLocal, engine
from .models import Device
def main():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        if db.query(Device).count(): print("База не пуста; демоданные не добавлены"); return
        db.add_all([Device(name="Коммутатор QTECH (демо)",ip_address="192.0.2.10",vendor="QTECH",model="QSW-4610-28T-AC",installed_version=None,acquisition_method="manual",auto_check=False),Device(name="Коммутатор Eltex (демо)",ip_address="192.0.2.11",vendor="Eltex",model="MES2428P",installed_version=None,acquisition_method="manual",auto_check=False),Device(name="Коммутатор D-Link (демо)",ip_address="192.0.2.12",vendor="D-Link",model="DGS-1100-08V2",hardware_revision="B1",installed_version=None,acquisition_method="manual",auto_check=False)])
        db.commit(); print("Демоданные добавлены")
if __name__ == "__main__": main()

