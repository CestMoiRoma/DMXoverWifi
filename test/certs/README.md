# Extra root certificates

Normally empty, and normally you can ignore this directory.

It exists for machines where something intercepts TLS: a corporate proxy, or an
antivirus product with an HTTPS scanning feature. On those machines the container
cannot verify pypi.org, and the build fails with:

```
SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate
verify failed: unable to get local issuer certificate'))
```

The fix is to trust the intercepting root inside the image. Drop it here as a
PEM file with a `.crt` extension and rebuild. The Dockerfile picks up anything in
this directory, installs it, and points pip at the updated bundle. With the
directory empty, that step does nothing.

Grabbing the root on Windows:

```powershell
$client = New-Object System.Net.Sockets.TcpClient('pypi.org', 443)
$ssl = New-Object System.Net.Security.SslStream($client.GetStream(), $false, ({$true}))
$ssl.AuthenticateAsClient('pypi.org')
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($ssl.RemoteCertificate)
$chain = New-Object System.Security.Cryptography.X509Certificates.X509Chain
$null = $chain.Build($cert)
$root = $chain.ChainElements[$chain.ChainElements.Count - 1].Certificate
$pem = "-----BEGIN CERTIFICATE-----`n" +
       [Convert]::ToBase64String($root.RawData, 'InsertLineBreaks') +
       "`n-----END CERTIFICATE-----`n"
Set-Content test/certs/local-interception-root.crt $pem -Encoding ascii
$ssl.Close(); $client.Close()
```

If the issuer that comes back is a real public CA, nothing is intercepting your
traffic and your build failure has another cause.

`.crt` files here are gitignored. They describe one machine's network, they are
not part of the project, and some of them identify an employer.
