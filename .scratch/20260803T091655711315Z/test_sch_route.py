"""sch_route.py için test suite (pytest) — Router/mst_order/junction_points.

Bu dosya `sch_wire.py`'nin sembol/kütüphane yükleme kısmına DOKUNMAZ (gerçek
KiCad sembol kütüphanesi gerektirir) — yalnızca `Router` A* motorunun ve
saf geometri yardımcılarının GERÇEKTEN çalıştığını, engelden kaçtığını ve
yabancı net'e kısa devreyi engellediğini kanıtlar.
"""

from __future__ import annotations

from sch_route import Router, junction_points, mst_order


def test_router_duz_hat_baglar():
    r = Router(size=(20.0, 20.0))
    hedef = (5 * r.grid, 0.0)  # grid'e hizalı hedef (Router hücre bazlı çalışır)
    path = r.route((0.0, 0.0), hedef, "NET1")
    assert path is not None
    assert path[0] == (0.0, 0.0)
    assert path[-1] == hedef


def test_router_blocked_hucre_etrafindan_dolanir():
    r = Router(size=(20.0, 20.0))
    # (0,0) ile (5,0) arasındaki TÜM y=0 hücrelerini blokla -> zorunlu dolanma
    for i in range(0, 6):
        r.blocked.add((i, 0))
    path = r.route((0.0, 1.27), (5 * r.grid, 1.27), "NET1")
    assert path is not None  # y=1.27 satırından gidebilmeli


def test_router_tamamen_engellenmis_hedefe_ulasamaz():
    r = Router(size=(20.0, 20.0))
    goal_cell = r.cell((5.0, 0.0))
    # Hedef hücrenin komşularını da blokla ki gerçekten ulaşılamaz olsun
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            if (dx, dy) != (0, 0):
                r.blocked.add((goal_cell[0] + dx, goal_cell[1] + dy))
    r.blocked.add(goal_cell)
    path = r.route((0.0, 0.0), (5.0, 0.0), "NET1")
    assert path is None


def test_router_yabanci_net_ucuna_short_olusturmaz():
    """İkinci net, ilk net'in tel UCUNA denk gelen bir hedefe route
    EDİLEMEMELİ — bu, KiCad'de sessiz kısa devre üreten tuzağın ta kendisi
    (bkz. modül docstring'i)."""
    r = Router(size=(20.0, 20.0))
    hedef = (5 * r.grid, 0.0)
    first = r.route((0.0, 0.0), hedef, "NET_A")
    assert first is not None
    r.commit(first, "NET_A")
    # NET_B, NET_A'nın UCUNA aynı noktaya varmaya çalışıyor -> reddedilmeli
    second = r.route((0.0, 2.54), hedef, "NET_B")
    assert second is None


def test_router_ayni_net_kendi_teline_deginebilir():
    r = Router(size=(20.0, 20.0))
    first = r.route((0.0, 0.0), (5 * r.grid, 0.0), "NET_A")
    r.commit(first, "NET_A")
    # Aynı net'in başka bir dalı aynı hatta uçlaşabilmeli (T-bağlantı istenir)
    second = r.route((2.54, 2.54), (2.54, 0.0), "NET_A")
    assert second is not None


def test_mst_order_bos_ve_tek_nokta():
    assert mst_order([]) == []
    assert mst_order([(0.0, 0.0)]) == []


def test_mst_order_uc_noktayi_baglar():
    pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    edges = mst_order(pts)
    assert len(edges) == 2
    baglanan = {0}
    for i, j in edges:
        assert i in baglanan
        baglanan.add(j)
    assert baglanan == {0, 1, 2}


def test_junction_points_t_baglantisini_bulur():
    polys_by_net = {
        "NET1": [
            [(0.0, 0.0), (10.0, 0.0)],
            [(5.0, 0.0), (5.0, 5.0)],  # ortadan T şeklinde dallanma
        ]
    }
    junctions = junction_points(polys_by_net)
    assert (5.0, 0.0) in junctions


def test_junction_points_ayrik_teller_junction_uretmez():
    polys_by_net = {"NET1": [[(0.0, 0.0), (10.0, 0.0)], [(20.0, 0.0), (30.0, 0.0)]]}
    assert junction_points(polys_by_net) == []
