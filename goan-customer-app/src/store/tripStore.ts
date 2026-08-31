import { create } from "zustand";
import type { Trip } from "@/types";

interface TripState {
  activeTrip: Trip | null;
  driverLocation: { lat: number; lng: number } | null;
  setActiveTrip: (trip: Trip | null) => void;
  updateTripStatus: (status: Trip["status"]) => void;
  setDriverLocation: (loc: { lat: number; lng: number }) => void;
  clear: () => void;
}

export const useTripStore = create<TripState>((set) => ({
  activeTrip: null,
  driverLocation: null,
  setActiveTrip: (trip) => set({ activeTrip: trip }),
  updateTripStatus: (status) =>
    set((state) => (state.activeTrip ? { activeTrip: { ...state.activeTrip, status } } : state)),
  setDriverLocation: (loc) => set({ driverLocation: loc }),
  clear: () => set({ activeTrip: null, driverLocation: null }),
}));
