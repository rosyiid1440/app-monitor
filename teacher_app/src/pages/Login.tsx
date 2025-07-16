import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useToast } from '@/hooks/use-toast';
import { Monitor } from 'lucide-react';

export default function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const { toast } = useToast();

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      // Menggunakan Basic Authentication header
      const headers = new Headers();
      headers.append('Authorization', 'Basic ' + btoa(username + ":" + password));

      const response = await fetch('/api/login', {
        method: 'POST',
        headers: headers,
      });

      if (response.ok) {
        // Jika login berhasil, tandai sesi sebagai "logged in"
        localStorage.setItem('isLoggedIn', 'true');
        toast({ title: "Login Berhasil", description: "Selamat datang kembali!" });
        navigate('/');
      } else {
        const errorData = await response.json();
        setError(errorData.detail || 'Username atau password salah.');
      }
    } catch (err) {
      setError('Gagal terhubung ke server. Pastikan server berjalan.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-background to-surface p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="text-center">
          <Monitor className="mx-auto h-12 w-12 text-primary" />
          <CardTitle className="mt-4">Dasbor Guru</CardTitle>
          <CardDescription>Silakan login untuk melanjutkan</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleLogin} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Username</Label>
              <Input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                placeholder="Masukkan username"
                disabled={isLoading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                placeholder="Masukkan password"
                disabled={isLoading}
              />
            </div>
            {error && <p className="text-sm font-medium text-destructive">{error}</p>}
            <Button type="submit" className="w-full" disabled={isLoading}>
              {isLoading ? 'Memproses...' : 'Login'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
