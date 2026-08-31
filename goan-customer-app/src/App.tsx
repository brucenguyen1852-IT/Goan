import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppLayout } from "@/components/layout/AppLayout";
import { RequireAuth } from "@/components/layout/RequireAuth";
import { LoginPage } from "@/pages/LoginPage";
import { OtpVerifyPage } from "@/pages/OtpVerifyPage";
import { HomePage } from "@/pages/HomePage";
import { TripTrackingPage } from "@/pages/TripTrackingPage";
import { TripHistoryPage } from "@/pages/TripHistoryPage";
import { ProfilePage } from "@/pages/ProfilePage";

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/otp" element={<OtpVerifyPage />} />

        <Route
          element={
            <RequireAuth>
              <AppLayout />
            </RequireAuth>
          }
        >
          <Route path="/" element={<HomePage />} />
          <Route path="/trip/:tripId" element={<TripTrackingPage />} />
          <Route path="/history" element={<TripHistoryPage />} />
          <Route path="/profile" element={<ProfilePage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
