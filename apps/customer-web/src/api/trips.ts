import { apiClient } from "@/api/client";
import type { FareEstimate, GeoPoint, PaymentMethod, Trip } from "@/types";

export async function getFareEstimate(
  pickup: GeoPoint,
  dropoff: GeoPoint,
  pickupAddress: string,
  dropoffAddress: string
): Promise<FareEstimate> {
  const { data } = await apiClient.post<FareEstimate>("/trips/fare-estimate", {
    pickup,
    dropoff,
    pickup_address: pickupAddress,
    dropoff_address: dropoffAddress,
  });
  return data;
}

export async function createTrip(params: {
  pickup: GeoPoint;
  dropoff: GeoPoint;
  pickup_address: string;
  dropoff_address: string;
  payment_method: PaymentMethod;
  partner_qr_code?: string;
}): Promise<Trip> {
  const { data } = await apiClient.post<Trip>("/trips", params);
  return data;
}

export async function getTrip(tripId: string): Promise<Trip> {
  const { data } = await apiClient.get<Trip>(`/trips/${tripId}`);
  return data;
}

export async function cancelTrip(tripId: string): Promise<Trip> {
  const { data } = await apiClient.post<Trip>(`/trips/${tripId}/cancel`);
  return data;
}
