import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout.jsx";
import Overview from "./pages/Overview.jsx";
import Keys from "./pages/Keys.jsx";
import Teams from "./pages/Teams.jsx";
import Models from "./pages/Models.jsx";
import Deployments from "./pages/Deployments.jsx";
import Playground from "./pages/Playground.jsx";
import Usage from "./pages/Usage.jsx";
import Audit from "./pages/Audit.jsx";
import Settings from "./pages/Settings.jsx";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="keys" element={<Keys />} />
        <Route path="teams" element={<Teams />} />
        <Route path="models" element={<Models />} />
        <Route path="deployments" element={<Deployments />} />
        <Route path="playground" element={<Playground />} />
        <Route path="usage" element={<Usage />} />
        <Route path="audit" element={<Audit />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  );
}
