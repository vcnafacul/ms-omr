from app.config import Settings


def test_worker_defaults():
    s = Settings()
    assert s.omr_max_workers >= 1
    assert s.omr_inprocess_worker is True


def test_teto_de_tentativas_tem_default_3():
    # pelo model_fields, e não por Settings().omr_max_tries, para não depender do .env da máquina
    assert Settings.model_fields["omr_max_tries"].default == 3


def test_worker_e_pipeline_leem_o_mesmo_teto_de_tentativas():
    from app.config import get_settings
    from app.worker import WorkerSettings

    assert WorkerSettings.max_tries == get_settings().omr_max_tries
