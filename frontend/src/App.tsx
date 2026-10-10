import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Shell } from "@/components/layout/Shell";
import { ForbiddenState } from "@/components/ui/primitives";
import { AdminPage } from "@/features/administration/AdminPage";
import { AiSettingsPage } from "@/features/ai-settings/AiSettingsPage";
import { SavingsPage } from "@/features/analytics/SavingsPage";
import { RejectionsPage } from "@/features/analytics/RejectionsPage";
import { AuditPage } from "@/features/audit/AuditPage";
import { LoginPage } from "@/features/auth/LoginPage";
import { CopilotPage } from "@/features/copilot/CopilotPage";
import { DashboardPage } from "@/features/dashboard/DashboardPage";
import { ImportPage } from "@/features/data-import/ImportPage";
import { AnalysesPage, AnalysisDetailPage } from "@/features/duplicate-detection/AnalysisPages";
import { EvaluationPage } from "@/features/evaluation/EvaluationPage";
import { IdeaDetailPage, IdeasPage, SubmitPage } from "@/features/ideas/IdeaPages";
import { ReviewsPage } from "@/features/reviews/ReviewsPage";
import { useAuth } from "@/lib/auth";

function RequireAuth() {
  const { user, ready } = useAuth();
  if (!ready) return <p className="p-8 text-sm text-muted">Checking session…</p>;
  if (!user) return <Navigate to="/login" replace />;
  return <Shell />;
}

function Guard({ permission, children }: { permission?: string; children: ReactNode }) {
  const { allowed } = useAuth();
  if (!allowed(permission)) return <ForbiddenState />;
  return children;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route index element={<Guard permission="dashboard:read"><DashboardPage /></Guard>} />
        <Route path="ideas" element={<Guard permission="ideas:read"><IdeasPage /></Guard>} />
        <Route path="ideas/new" element={<Guard permission="ideas:write"><SubmitPage /></Guard>} />
        <Route path="ideas/:ideaId" element={<Guard permission="ideas:read"><IdeaDetailPage /></Guard>} />
        <Route path="analyses" element={<Guard permission="ideas:read"><AnalysesPage /></Guard>} />
        <Route path="analyses/:analysisId" element={<Guard permission="ideas:read"><AnalysisDetailPage /></Guard>} />
        <Route path="reviews" element={<Guard permission="reviews:read"><ReviewsPage /></Guard>} />
        <Route path="import" element={<Guard permission="ideas:import"><ImportPage /></Guard>} />
        <Route path="analytics/savings" element={<Guard permission="analytics:read"><SavingsPage /></Guard>} />
        <Route path="analytics/rejections" element={<Guard permission="analytics:read"><RejectionsPage /></Guard>} />
        <Route path="copilot" element={<Guard permission="copilot:use"><CopilotPage /></Guard>} />
        <Route path="evaluation" element={<Guard permission="evaluation:read"><EvaluationPage /></Guard>} />
        <Route path="settings/ai" element={<AiSettingsPage />} />
        <Route path="audit" element={<Guard permission="audit:read"><AuditPage /></Guard>} />
        <Route path="admin" element={<Guard permission="*"><AdminPage /></Guard>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
