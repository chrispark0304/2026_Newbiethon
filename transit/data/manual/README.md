# 수동 보정 데이터

여기 있는 값은 **자동 수집 결과를 항상 덮어쓴다.** 자동 수집이 틀렸을 때만 쓴다.

## station_coords_override.csv

`station_name,lat,lon,source` 형식. 예:

```csv
station_name,lat,lon,source
총신대입구,37.4867800,126.9822371,manual
```

역 좌표는 OSM 릴레이션 노드에서 자동으로 나온다. OSM 값이 틀렸을 때만 여기에 추가한다.
