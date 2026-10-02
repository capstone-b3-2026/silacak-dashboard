from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/terrain", tags=["terrain"])


@router.get("/profile")
async def terrain_profile(from_lat: float, from_lon: float, to_lat: float, to_lon: float):
    """
    TODO (belum diimplementasikan):
    Sampling elevasi dari file DEM (GeoTIFF DEMNAS) di sepanjang garis
    from -> to, buat hitung clearance zona Fresnel antar dua titik node
    LoRa. Rencana implementasi:

    1. Taruh file .tif hasil clip DEMNAS di /app/data/dem/
    2. Baca pakai rasterio, sample tiap ~10m sepanjang garis
    3. Hitung radius Fresnel zone pertama tiap titik sampel:
       r = 17.3 * sqrt((d1*d2) / (f*d))   [d1,d2 km, f GHz, r meter]
    4. Bandingkan elevasi tanah + 60% radius Fresnel vs garis LOS
       (interpolasi linear ketinggian antena dua node)
    5. Return array {distance_m, ground_elevation, los_elevation,
       fresnel_lower, fresnel_upper, clear: bool}

    Dipakai buat fitur "Network Planner" - alat bantu nentuin posisi
    optimal node sebelum deployment ke gunung.
    """
    raise HTTPException(
        status_code=501,
        detail="Terrain profile belum diimplementasi - butuh file DEM di data/dem/ dulu",
    )
