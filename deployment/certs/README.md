Drop internal root CA certificates here as *.pem (e.g. the VW root CA). They are concatenated into ca-bundle.pem at image build time and trusted by requests (DQN API) and OpenSSL. Nothing here is required when the endpoints use publicly trusted certificates.

