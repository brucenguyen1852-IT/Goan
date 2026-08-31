export interface GeoPoint {
  lat: number;
  lng: number;
}

export interface FareEstimate {
  time_band: "normal" | "night" | "peak";
  distance_km: number;
  duration_min: number;
  base_fare: number;
  distance_fare: number;
  time_fare: number;
  surcharge_far_pickup: number;
  total_fare_estimate: number;
}

export type PaymentMethod = "online" | "cash";

export type TripStatus =
  | "requested"
  | "matching"
  | "driver_assigned"
  | "driver_arriving"
  | "qr_verified"
  | "in_progress"
  | "completed"
  | "rated"
  | "cancelled_by_customer"
  | "cancelled_by_driver"
  | "no_driver_found";

export interface Trip {
  id: string;
  status: TripStatus;
  pickup_address: string;
  dropoff_address: string;
  total_fare: number | null;
  driver_id: string | null;
  requested_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}
