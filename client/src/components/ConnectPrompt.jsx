import { Link } from "react-router-dom";
import { PlugZap } from "lucide-react";
import { Card, EmptyState, Button } from "./ui.jsx";

export function ConnectPrompt({ what = "this page" }) {
  return (
    <Card>
      <EmptyState
        icon={PlugZap}
        title="Connect your gateway"
        description={`Set an admin token to use ${what}. Admin endpoints require the X-Admin-Token header.`}
        action={
          <Link to="/settings">
            <Button>Go to Settings</Button>
          </Link>
        }
      />
    </Card>
  );
}
