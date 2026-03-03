"use client";

import { useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { Mail } from "lucide-react";

import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();

    if (password !== confirmPassword) {
      toast.error("Die Passwörter stimmen nicht überein.");
      return;
    }

    setIsLoading(true);

    const supabase = createClient();
    const { error } = await supabase.auth.signUp({ email, password });

    if (error) {
      toast.error(error.message);
      setIsLoading(false);
      return;
    }

    setIsSuccess(true);
    setIsLoading(false);
  }

  if (isSuccess) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-xl font-semibold">E-Mail bestätigen</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-4 py-4">
          <Mail className="size-10 text-muted-foreground" />
          <p className="text-center text-sm text-muted-foreground">
            Wir haben eine Bestätigungs-E-Mail an{" "}
            <span className="font-medium text-foreground">{email}</span>{" "}
            gesendet. Bitte überprüfe dein Postfach.
          </p>
        </CardContent>
        <CardFooter className="justify-center">
          <Link
            href="/login"
            className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            Zurück zur Anmeldung
          </Link>
        </CardFooter>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl font-semibold">Konto erstellen</CardTitle>
      </CardHeader>

      <CardContent>
        <form id="signup-form" onSubmit={handleSubmit} className="flex flex-col gap-5">
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">E-Mail</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              placeholder="name@beispiel.at"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isLoading}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Passwort</Label>
            <Input
              id="password"
              type="password"
              autoComplete="new-password"
              placeholder="••••••••"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label htmlFor="confirm-password">Passwort bestätigen</Label>
            <Input
              id="confirm-password"
              type="password"
              autoComplete="new-password"
              placeholder="••••••••"
              required
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={isLoading}
            />
          </div>

          <Button
            type="submit"
            form="signup-form"
            className="w-full"
            disabled={isLoading}
          >
            {isLoading ? "Registrieren..." : "Registrieren"}
          </Button>
        </form>
      </CardContent>

      <CardFooter className="justify-center">
        <p className="text-sm text-muted-foreground">
          Bereits registriert?{" "}
          <Link
            href="/login"
            className="underline-offset-4 hover:text-foreground hover:underline"
          >
            Anmelden
          </Link>
        </p>
      </CardFooter>
    </Card>
  );
}
