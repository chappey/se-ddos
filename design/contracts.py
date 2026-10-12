"""
DroneDash CLE (CLE_DDOS) — Formal Executable Specification
============================================================
This module serves as the machine-executable contract for CLE_DDOS.
It codifies enums, data structures, state transition invariants,
geofencing algorithms, scheduling rules, energy physics, and simulation
telemetry in 100% standard Python (no external dependencies required).

Run directly to verify system invariants:
    python3 design/contracts.py
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Set, Tuple, List, Dict
import math


# ==============================================================================
# 1. Enums
# ==============================================================================

class OrderStatus(str, Enum):
    REQUESTED = "REQUESTED"
    ACCEPTED = "ACCEPTED"
    SCHEDULED = "SCHEDULED"
    ASSIGNED = "ASSIGNED"
    IN_TRANSIT = "IN_TRANSIT"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    RESCHEDULING_REQUIRED = "RESCHEDULING_REQUIRED"


class DroneStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    ASSIGNED = "ASSIGNED"
    IN_FLIGHT = "IN_FLIGHT"
    CHARGING = "CHARGING"
    MAINTENANCE = "MAINTENANCE"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"


class FlightPhase(str, Enum):
    CLIMB = "CLIMB"
    CRUISE = "CRUISE"
    DESCEND = "DESCEND"
    LANDED = "LANDED"


class DeliveryPriority(str, Enum):
    STANDARD = "STANDARD"
    EXPRESS = "EXPRESS"


class ZoneType(str, Enum):
    COMMERCIAL = "COMMERCIAL"
    RESIDENTIAL = "RESIDENTIAL"
    INDUSTRIAL = "INDUSTRIAL"


class RestrictionType(str, Enum):
    TEMPORARY = "TEMPORARY"
    PERMANENT = "PERMANENT"


class ExceptionType(str, Enum):
    INSUFFICIENT_BATTERY = "INSUFFICIENT_BATTERY"
    WEATHER_RESTRICTION = "WEATHER_RESTRICTION"
    RESTRICTED_AIRSPACE = "RESTRICTED_AIRSPACE"
    DRONE_MALFUNCTION = "DRONE_MALFUNCTION"
    PACKAGE_PROBLEM = "PACKAGE_PROBLEM"
    DESTINATION_UNAVAILABLE = "DESTINATION_UNAVAILABLE"


# ==============================================================================
# 2. State Transition Invariants & Limits
# ==============================================================================

MAX_RESCHEDULING_RETRIES: int = 3
CRUISE_SPEED_MPH: float = 30.0
CRUISE_ALTITUDE_FEET: float = 200.0
BASE_CONSUMPTION_RATE_PCT_PER_MILE: float = 1.5
RESERVE_MARGIN_PCT: float = 20.0  # Mandatory 20% safety buffer

VALID_ORDER_TRANSITIONS: Dict[OrderStatus, Set[OrderStatus]] = {
    OrderStatus.REQUESTED: {OrderStatus.ACCEPTED, OrderStatus.CANCELLED},
    OrderStatus.ACCEPTED: {OrderStatus.SCHEDULED, OrderStatus.CANCELLED},
    OrderStatus.SCHEDULED: {OrderStatus.ASSIGNED, OrderStatus.RESCHEDULING_REQUIRED, OrderStatus.CANCELLED},
    OrderStatus.ASSIGNED: {OrderStatus.IN_TRANSIT, OrderStatus.SCHEDULED, OrderStatus.CANCELLED},
    OrderStatus.IN_TRANSIT: {OrderStatus.DELIVERED, OrderStatus.FAILED, OrderStatus.RESCHEDULING_REQUIRED},
    OrderStatus.RESCHEDULING_REQUIRED: {OrderStatus.SCHEDULED, OrderStatus.CANCELLED, OrderStatus.FAILED},
    OrderStatus.DELIVERED: set(),  # Terminal
    OrderStatus.CANCELLED: set(),  # Terminal
    OrderStatus.FAILED: set(),     # Terminal
}

VALID_DRONE_TRANSITIONS: Dict[DroneStatus, Set[DroneStatus]] = {
    DroneStatus.AVAILABLE: {DroneStatus.ASSIGNED, DroneStatus.CHARGING, DroneStatus.MAINTENANCE, DroneStatus.OUT_OF_SERVICE},
    DroneStatus.ASSIGNED: {DroneStatus.IN_FLIGHT, DroneStatus.AVAILABLE, DroneStatus.MAINTENANCE},
    DroneStatus.IN_FLIGHT: {DroneStatus.AVAILABLE, DroneStatus.CHARGING, DroneStatus.MAINTENANCE},
    DroneStatus.CHARGING: {DroneStatus.AVAILABLE, DroneStatus.MAINTENANCE, DroneStatus.OUT_OF_SERVICE},
    DroneStatus.MAINTENANCE: {DroneStatus.CHARGING, DroneStatus.AVAILABLE, DroneStatus.OUT_OF_SERVICE},
    DroneStatus.OUT_OF_SERVICE: {DroneStatus.MAINTENANCE},
}

PRE_TRANSIT_CANCELLABLE_STATES: Set[OrderStatus] = {
    OrderStatus.REQUESTED,
    OrderStatus.ACCEPTED,
    OrderStatus.SCHEDULED,
    OrderStatus.ASSIGNED,
}


def can_transition_order(current: OrderStatus, target: OrderStatus) -> bool:
    """Validate whether an order state transition is permitted."""
    return target in VALID_ORDER_TRANSITIONS.get(current, set())


def can_transition_drone(current: DroneStatus, target: DroneStatus) -> bool:
    """Validate whether a drone state transition is permitted."""
    return target in VALID_DRONE_TRANSITIONS.get(current, set())


def can_cancel_order(current: OrderStatus) -> bool:
    """Customers can only cancel prior to dispatch (in-transit lockout)."""
    return current in PRE_TRANSIT_CANCELLABLE_STATES


def check_rescheduling_retry_limit(retry_count: int) -> OrderStatus:
    """Determine whether an order can be rescheduled or must transition to FAILED."""
    if retry_count < MAX_RESCHEDULING_RETRIES:
        return OrderStatus.SCHEDULED
    return OrderStatus.FAILED


# ==============================================================================
# 3. Spatial Math, Bounding Boxes & Geofencing
# ==============================================================================

@dataclass(frozen=True)
class Coordinates:
    latitude: float
    longitude: float


@dataclass(frozen=True)
class BoundingBox:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    def contains(self, coord: Coordinates) -> bool:
        return (self.min_lat <= coord.latitude <= self.max_lat and
                self.min_lon <= coord.longitude <= self.max_lon)


# Cleveland Metropolitan Operating Bounding Box (from SRS Section 8.2)
CLEVELAND_BBOX = BoundingBox(
    min_lat=41.2,
    max_lat=41.7,
    min_lon=-81.9,
    max_lon=-81.4
)


def haversine_distance_miles(p1: Coordinates, p2: Coordinates) -> float:
    """Compute great-circle distance between two GPS coordinates in statute miles."""
    earth_radius_miles = 3958.8
    lat1_rad = math.radians(p1.latitude)
    lat2_rad = math.radians(p2.latitude)
    delta_lat = math.radians(p2.latitude - p1.latitude)
    delta_lon = math.radians(p2.longitude - p1.longitude)

    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_miles * c


@dataclass
class AirspacePolygon:
    id: str
    name: str
    vertices: List[Coordinates]
    is_active: bool = True
    restriction_type: RestrictionType = RestrictionType.PERMANENT
    bbox: BoundingBox = field(init=False)

    def __post_init__(self):
        if len(self.vertices) < 3:
            raise ValueError(f"Polygon {self.id} must have at least 3 vertices.")
        lats = [v.latitude for v in self.vertices]
        lons = [v.longitude for v in self.vertices]
        self.bbox = BoundingBox(
            min_lat=min(lats),
            max_lat=max(lats),
            min_lon=min(lons),
            max_lon=max(lons)
        )

    def contains_point(self, pt: Coordinates) -> bool:
        """Ray-casting point-in-polygon algorithm with bounding box fast-reject."""
        if not self.bbox.contains(pt):
            return False

        inside = False
        n = len(self.vertices)
        p1 = self.vertices[0]
        for idx in range(1, n + 1):
            p2 = self.vertices[idx % n]
            if pt.longitude > min(p1.longitude, p2.longitude):
                if pt.longitude <= max(p1.longitude, p2.longitude):
                    if pt.latitude <= max(p1.latitude, p2.latitude):
                        if p1.longitude != p2.longitude:
                            xinters = (pt.longitude - p1.longitude) * (p2.latitude - p1.latitude) / (p2.longitude - p1.longitude) + p1.latitude
                            if p1.latitude == p2.latitude or pt.latitude <= xinters:
                                inside = not inside
            p1 = p2
        return inside


def _ccw(A: Coordinates, B: Coordinates, C: Coordinates) -> bool:
    """Test whether three points are listed in counterclockwise order."""
    return (C.longitude - A.longitude) * (B.latitude - A.latitude) > (B.longitude - A.longitude) * (C.latitude - A.latitude)


def line_segments_intersect(A: Coordinates, B: Coordinates, C: Coordinates, D: Coordinates) -> bool:
    """Return True if line segment AB intersects line segment CD."""
    return (_ccw(A, C, D) != _ccw(B, C, D)) and (_ccw(A, B, C) != _ccw(A, B, D))


def path_intersects_polygon(origin: Coordinates, destination: Coordinates, polygon: AirspacePolygon) -> bool:
    """
    Check if straight-line trajectory intersects an active restricted polygon
    either by crossing polygon boundaries or having an endpoint inside.
    """
    if not polygon.is_active:
        return False

    # Check if either endpoint lies inside the polygon
    if polygon.contains_point(origin) or polygon.contains_point(destination):
        return True

    # Check segment intersection against every polygon boundary edge
    n = len(polygon.vertices)
    for idx in range(n):
        v1 = polygon.vertices[idx]
        v2 = polygon.vertices[(idx + 1) % n]
        if line_segments_intersect(origin, destination, v1, v2):
            return True

    return False


# Canonical Cleveland Base Stations (from SRS Section 11.1 and 16)
CANONICAL_STATIONS: Dict[str, dict] = {
    "STATION-01": {
        "name": "Public Square Hub (Downtown)",
        "coords": Coordinates(latitude=41.4993, longitude=-81.6944),
        "total_docks": 5,
    },
    "STATION-02": {
        "name": "University Circle Hub (East Side)",
        "coords": Coordinates(latitude=41.5075, longitude=-81.6083),
        "total_docks": 4,
    },
    "STATION-03": {
        "name": "Ohio City Hub (West Side)",
        "coords": Coordinates(latitude=41.4842, longitude=-81.7056),
        "total_docks": 3,
    },
}

# Canonical Restricted Airspace Polygons (Burke Lakefront Airport & Hopkins Approach)
CANONICAL_RESTRICTIONS: List[AirspacePolygon] = [
    AirspacePolygon(
        id="RESTRICT-BURKE",
        name="Burke Lakefront Airport Airspace (KBKL)",
        vertices=[
            Coordinates(latitude=41.5140, longitude=-81.6900),
            Coordinates(latitude=41.5250, longitude=-81.6700),
            Coordinates(latitude=41.5200, longitude=-81.6500),
            Coordinates(latitude=41.5080, longitude=-81.6680),
        ],
        is_active=True,
        restriction_type=RestrictionType.PERMANENT,
    ),
    AirspacePolygon(
        id="RESTRICT-STADIUM",
        name="Cleveland Browns Stadium Game-Day TFR",
        vertices=[
            Coordinates(latitude=41.5040, longitude=-81.7010),
            Coordinates(latitude=41.5080, longitude=-81.7010),
            Coordinates(latitude=41.5080, longitude=-81.6970),
            Coordinates(latitude=41.5040, longitude=-81.6970),
        ],
        is_active=True,
        restriction_type=RestrictionType.TEMPORARY,
    ),
]


# ==============================================================================
# 4. Energy Model & Payload Scaling
# ==============================================================================

def compute_payload_scaled_rate(
    package_weight_lbs: float,
    drone_max_payload_lbs: float,
    base_rate_pct_per_mile: float = BASE_CONSUMPTION_RATE_PCT_PER_MILE,
) -> float:
    """
    Normalized Linear Payload Scaling:
    rate(weight) = base_rate * (1 + weight / max_payload)
    Empty/unladen uses base_rate; 100% capacity uses 2x base_rate.
    """
    if drone_max_payload_lbs <= 0:
        raise ValueError("Drone max payload must be positive.")
    weight_ratio = max(0.0, min(package_weight_lbs / drone_max_payload_lbs, 1.0))
    return base_rate_pct_per_mile * (1.0 + weight_ratio)


def compute_mission_required_battery_pct(
    ferry_to_pickup_miles: float,
    delivery_leg_miles: float,
    recovery_leg_miles: float,
    package_weight_lbs: float,
    drone_max_payload_lbs: float,
    base_rate_pct_per_mile: float = BASE_CONSUMPTION_RATE_PCT_PER_MILE,
    reserve_margin_pct: float = RESERVE_MARGIN_PCT,
) -> float:
    """
    Calculate total energy needed across all 3 mission legs plus 20% reserve:
      - Leg 1: Station to Pickup (Unladen -> base_rate)
      - Leg 2: Pickup to Destination (Laden -> payload-scaled rate)
      - Leg 3: Destination to Recovery Station (Unladen -> base_rate)
    """
    unladen_rate = base_rate_pct_per_mile
    laden_rate = compute_payload_scaled_rate(package_weight_lbs, drone_max_payload_lbs, base_rate_pct_per_mile)

    leg1_energy = ferry_to_pickup_miles * unladen_rate
    leg2_energy = delivery_leg_miles * laden_rate
    leg3_energy = recovery_leg_miles * unladen_rate

    total_flight_energy = leg1_energy + leg2_energy + leg3_energy
    return total_flight_energy + reserve_margin_pct


# ==============================================================================
# 5. Scheduling, Dispatch & Tie-Breaking Engine
# ==============================================================================

@dataclass
class PackageSpec:
    id: str
    weight_lbs: float
    length_in: float
    width_in: float
    height_in: float


@dataclass
class DroneSpec:
    id: str
    model: str
    max_payload_lbs: float
    max_flight_range_miles: float
    battery_level_pct: float
    status: DroneStatus
    current_location: Coordinates
    current_station_id: str
    base_consumption_rate: float = BASE_CONSUMPTION_RATE_PCT_PER_MILE


@dataclass
class OrderQueueItem:
    order_id: str
    priority: DeliveryPriority
    created_at_timestamp: float
    package: PackageSpec
    pickup_coords: Coordinates
    delivery_coords: Coordinates
    retry_count: int = 0


def sort_order_queue(items: List[OrderQueueItem]) -> List[OrderQueueItem]:
    """
    Sort pending orders:
    1. Priority tier (EXPRESS before STANDARD)
    2. FIFO order creation timestamp
    """
    def queue_key(item: OrderQueueItem):
        priority_rank = 0 if item.priority == DeliveryPriority.EXPRESS else 1
        return (priority_rank, item.created_at_timestamp)

    return sorted(items, key=queue_key)


def rank_eligible_drones(
    drones: List[DroneSpec],
    package: PackageSpec,
    pickup_coords: Coordinates,
    delivery_coords: Coordinates,
    recovery_coords: Coordinates,
    active_restrictions: Optional[List[AirspacePolygon]] = None,
) -> List[Tuple[DroneSpec, float]]:
    """
    Evaluate and rank all drones that satisfy feasibility constraints.
    Returns list of (drone, required_battery_pct) sorted by:
      1. Proximity to pickup (ascending)
      2. Payload capacity margin: max_payload - package.weight (ascending - tighter fit conserves heavy-lifters)
      3. Battery level (descending)
      4. Drone ID (ascending deterministic)
    """
    if active_restrictions is None:
        active_restrictions = []

    # Verify flight paths do not intersect active restricted airspace
    delivery_dist = haversine_distance_miles(pickup_coords, delivery_coords)
    recovery_dist = haversine_distance_miles(delivery_coords, recovery_coords)

    for polygon in active_restrictions:
        if path_intersects_polygon(pickup_coords, delivery_coords, polygon):
            return []  # Delivery path blocked by restricted zone

    eligible_candidates = []

    for drone in drones:
        if drone.status != DroneStatus.AVAILABLE:
            continue
        if package.weight_lbs > drone.max_payload_lbs:
            continue

        ferry_dist = haversine_distance_miles(drone.current_location, pickup_coords)
        total_mission_distance = ferry_dist + delivery_dist + recovery_dist

        if total_mission_distance > drone.max_flight_range_miles:
            continue

        # Check if ferry leg intersects restricted zone
        ferry_blocked = False
        for polygon in active_restrictions:
            if path_intersects_polygon(drone.current_location, pickup_coords, polygon):
                ferry_blocked = True
                break
        if ferry_blocked:
            continue

        req_battery = compute_mission_required_battery_pct(
            ferry_to_pickup_miles=ferry_dist,
            delivery_leg_miles=delivery_dist,
            recovery_leg_miles=recovery_dist,
            package_weight_lbs=package.weight_lbs,
            drone_max_payload_lbs=drone.max_payload_lbs,
            base_rate_pct_per_mile=drone.base_consumption_rate,
        )

        if drone.battery_level_pct >= req_battery:
            eligible_candidates.append((drone, req_battery, ferry_dist))

    # Multi-attribute sort:
    # 1. Proximity (ferry_dist asc)
    # 2. Payload Fit: max_payload - weight (asc)
    # 3. Battery level (desc)
    # 4. Drone ID (asc)
    def ranking_key(entry):
        d, req_bat, dist = entry
        payload_margin = d.max_payload_lbs - package.weight_lbs
        return (dist, payload_margin, -d.battery_level_pct, d.id)

    sorted_candidates = sorted(eligible_candidates, key=ranking_key)
    return [(entry[0], entry[1]) for entry in sorted_candidates]


# ==============================================================================
# 6. In-Flight Telemetry & Simulation Physics
# ==============================================================================

@dataclass
class TelemetryPacket:
    timestamp_sec: float
    drone_id: str
    phase: FlightPhase
    latitude: float
    longitude: float
    altitude_feet: float
    speed_mph: float
    battery_pct: float
    distance_remaining_miles: float


def simulate_flight_tick(
    current_coords: Coordinates,
    target_coords: Coordinates,
    current_altitude_ft: float,
    current_battery_pct: float,
    current_phase: FlightPhase,
    weight_carried_lbs: float,
    max_payload_lbs: float,
    delta_time_sec: float = 1.0,
    cruise_speed_mph: float = CRUISE_SPEED_MPH,
    target_cruise_alt_ft: float = CRUISE_ALTITUDE_FEET,
    base_rate_pct_per_mile: float = BASE_CONSUMPTION_RATE_PCT_PER_MILE,
) -> Tuple[Coordinates, float, float, FlightPhase]:
    """
    Simulate a discrete time step (1-second tick) for drone flight:
      - 3-Phase Profile: CLIMB (0->200 ft), CRUISE (30 mph @ 200 ft), DESCEND (200->0 ft)
      - Computes step distance, battery decay, and updated coordinates.
    """
    total_dist = haversine_distance_miles(current_coords, target_coords)
    step_distance_miles = (cruise_speed_mph / 3600.0) * delta_time_sec

    # Battery consumption for this tick
    rate = compute_payload_scaled_rate(weight_carried_lbs, max_payload_lbs, base_rate_pct_per_mile)
    energy_consumed = step_distance_miles * rate
    new_battery = max(0.0, current_battery_pct - energy_consumed)

    # Reached destination
    if step_distance_miles >= total_dist:
        return target_coords, 0.0, new_battery, FlightPhase.LANDED

    # Positional interpolation along great circle
    ratio = step_distance_miles / total_dist
    new_lat = current_coords.latitude + (target_coords.latitude - current_coords.latitude) * ratio
    new_lon = current_coords.longitude + (target_coords.longitude - current_coords.longitude) * ratio
    new_coords = Coordinates(new_lat, new_lon)

    # 3-Phase Altitude Profile
    climb_rate_fps = 15.0  # 15 ft/sec vertical climb
    descent_rate_fps = 15.0
    descent_dist_threshold = (target_cruise_alt_ft / descent_rate_fps) * (cruise_speed_mph / 3600.0)

    if total_dist <= descent_dist_threshold:
        # Descend phase
        new_phase = FlightPhase.DESCEND
        new_alt = max(0.0, current_altitude_ft - (descent_rate_fps * delta_time_sec))
    elif current_altitude_ft < target_cruise_alt_ft:
        # Climb phase
        new_phase = FlightPhase.CLIMB
        new_alt = min(target_cruise_alt_ft, current_altitude_ft + (climb_rate_fps * delta_time_sec))
    else:
        # Cruise phase
        new_phase = FlightPhase.CRUISE
        new_alt = target_cruise_alt_ft

    return new_coords, new_alt, new_battery, new_phase


# ==============================================================================
# 7. Station Docking & Atomic RTB Mechanics
# ==============================================================================

@dataclass
class StationState:
    id: str
    name: str
    coords: Coordinates
    total_docks: int
    available_docks: int

    def reserve_dock(self) -> bool:
        """Atomically lock a docking spot for an incoming or aborting drone."""
        if self.available_docks > 0:
            self.available_docks -= 1
            return True
        return False

    def release_dock(self) -> None:
        """Release a docking spot when a drone departs."""
        if self.available_docks < self.total_docks:
            self.available_docks += 1


def find_nearest_recovery_station(
    drone_current_coords: Coordinates,
    drone_battery_pct: float,
    stations: List[StationState],
    base_rate_pct_per_mile: float = BASE_CONSUMPTION_RATE_PCT_PER_MILE,
) -> Optional[StationState]:
    """
    Locate closest station with available_docks > 0 that is reachable
    within remaining battery energy.
    """
    eligible_stations = []
    for st in stations:
        if st.available_docks <= 0:
            continue
        dist = haversine_distance_miles(drone_current_coords, st.coords)
        req_energy = dist * base_rate_pct_per_mile
        if drone_battery_pct >= req_energy:
            eligible_stations.append((st, dist))

    if not eligible_stations:
        return None

    # Pick station with minimum distance
    eligible_stations.sort(key=lambda pair: pair[1])
    return eligible_stations[0][0]


# ==============================================================================
# 8. Formal Contract Self-Test Suite
# ==============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("CLE_DDOS Formal Specification: Executing Verification Suite...")
    print("=" * 70)

    # 1. State Transitions & Invariants
    assert can_transition_order(OrderStatus.REQUESTED, OrderStatus.ACCEPTED)
    assert can_transition_order(OrderStatus.ASSIGNED, OrderStatus.IN_TRANSIT)
    assert not can_transition_order(OrderStatus.REQUESTED, OrderStatus.IN_TRANSIT)
    assert not can_transition_order(OrderStatus.DELIVERED, OrderStatus.REQUESTED)
    assert can_cancel_order(OrderStatus.ASSIGNED)
    assert not can_cancel_order(OrderStatus.IN_TRANSIT)  # In-flight cancellation lockout

    # 2. Rescheduling Retry Invariant
    assert check_rescheduling_retry_limit(0) == OrderStatus.SCHEDULED
    assert check_rescheduling_retry_limit(2) == OrderStatus.SCHEDULED
    assert check_rescheduling_retry_limit(3) == OrderStatus.FAILED  # 3 attempts exceeded

    # 3. Spatial Math & Cleveland Geofencing
    downtown = Coordinates(41.4993, -81.6944)
    university_circle = Coordinates(41.5075, -81.6083)
    dist = haversine_distance_miles(downtown, university_circle)
    assert 4.0 < dist < 5.0, f"Distance {dist:.2f} mi downtown->UC unexpected."
    assert CLEVELAND_BBOX.contains(downtown)
    assert CLEVELAND_BBOX.contains(university_circle)

    # Point-in-polygon verification (Burke Lakefront Airport)
    burke_poly = CANONICAL_RESTRICTIONS[0]
    point_inside_burke = Coordinates(41.5170, -81.6750)
    point_outside_burke = Coordinates(41.4993, -81.6944)
    assert burke_poly.contains_point(point_inside_burke), "Expected point inside Burke airspace."
    assert not burke_poly.contains_point(point_outside_burke), "Expected point outside Burke airspace."

    # Segment intersection test
    west_of_burke = Coordinates(41.5200, -81.7000)
    east_of_burke = Coordinates(41.5200, -81.6400)
    assert path_intersects_polygon(west_of_burke, east_of_burke, burke_poly), "Trajectory across Burke should be intercepted."

    # 4. Energy Model & Payload Scaling
    base_rate = 1.5
    rate_empty = compute_payload_scaled_rate(0.0, 10.0, base_rate)
    rate_half = compute_payload_scaled_rate(5.0, 10.0, base_rate)
    rate_full = compute_payload_scaled_rate(10.0, 10.0, base_rate)
    assert rate_empty == 1.5
    assert rate_half == 2.25
    assert rate_full == 3.0

    # Total mission required battery with 20% reserve
    req_bat = compute_mission_required_battery_pct(
        ferry_to_pickup_miles=2.0,
        delivery_leg_miles=4.0,
        recovery_leg_miles=2.0,
        package_weight_lbs=5.0,
        drone_max_payload_lbs=10.0,
    )
    # Leg 1: 2 * 1.5 = 3.0%
    # Leg 2: 4 * 2.25 = 9.0%
    # Leg 3: 2 * 1.5 = 3.0%
    # Total flight = 15.0% + 20% buffer = 35.0%
    assert abs(req_bat - 35.0) < 1e-4, f"Expected 35.0% required battery, got {req_bat}"

    # 5. Scheduling & Proximity Tie-Break
    pkg = PackageSpec("P-1", weight_lbs=4.0, length_in=8, width_in=6, height_in=4)
    pickup = Coordinates(41.5000, -81.6800)
    delivery = Coordinates(41.5100, -81.6500)
    recovery = downtown

    d1 = DroneSpec("D-FAR", "HeavyLifter", max_payload_lbs=20.0, max_flight_range_miles=30.0,
                   battery_level_pct=90.0, status=DroneStatus.AVAILABLE, current_location=university_circle, current_station_id="STATION-02")
    d2_heavy = DroneSpec("D-NEAR-HEAVY", "HeavyLifter", max_payload_lbs=20.0, max_flight_range_miles=30.0,
                         battery_level_pct=90.0, status=DroneStatus.AVAILABLE, current_location=downtown, current_station_id="STATION-01")
    d3_fit = DroneSpec("D-NEAR-FIT", "LightCargo", max_payload_lbs=6.0, max_flight_range_miles=30.0,
                       battery_level_pct=90.0, status=DroneStatus.AVAILABLE, current_location=downtown, current_station_id="STATION-01")

    ranked = rank_eligible_drones([d1, d2_heavy, d3_fit], pkg, pickup, delivery, recovery)
    assert len(ranked) == 3
    # Both d2 and d3 are close (at downtown), but d3 is smaller payload fit (6 lbs vs 20 lbs) -> d3 selected first!
    assert ranked[0][0].id == "D-NEAR-FIT", f"Expected D-NEAR-FIT first, got {ranked[0][0].id}"
    assert ranked[1][0].id == "D-NEAR-HEAVY"
    assert ranked[2][0].id == "D-FAR"

    # Queue ordering: Express ahead of Standard
    q_std = OrderQueueItem("ORD-1", DeliveryPriority.STANDARD, 100.0, pkg, pickup, delivery)
    q_exp = OrderQueueItem("ORD-2", DeliveryPriority.EXPRESS, 120.0, pkg, pickup, delivery)
    q_sorted = sort_order_queue([q_std, q_exp])
    assert q_sorted[0].order_id == "ORD-2", "Express order must preempt Standard order in queue."

    # 6. Telemetry & Simulation Physics Tick
    next_coords, alt, bat, phase = simulate_flight_tick(
        current_coords=downtown,
        target_coords=university_circle,
        current_altitude_ft=0.0,
        current_battery_pct=90.0,
        current_phase=FlightPhase.CLIMB,
        weight_carried_lbs=4.0,
        max_payload_lbs=10.0,
        delta_time_sec=1.0,
    )
    assert alt == 15.0  # Climbed 15 ft in 1 second
    assert phase == FlightPhase.CLIMB
    assert bat < 90.0

    # 7. Station Docking & Atomic RTB
    st1 = StationState("ST-1", "Public Square", downtown, total_docks=5, available_docks=1)
    st2 = StationState("ST-2", "University Circle", university_circle, total_docks=4, available_docks=0)
    nearest = find_nearest_recovery_station(downtown, drone_battery_pct=50.0, stations=[st1, st2])
    assert nearest is not None and nearest.id == "ST-1", "Only ST-1 had available docks."
    assert nearest.reserve_dock() is True
    assert nearest.available_docks == 0
    assert nearest.reserve_dock() is False  # Cannot reserve when 0 docks

    print("\n[SUCCESS] ALL FORMAL INVARIANTS, GEOFENCES, SCHEDULER RULES, AND PHYSICS VALIDATED!")
    print("=" * 70)
