from Crypto.Cipher import AES
from Crypto.Hash import SHA256
from Crypto import Random
import base64


class aes_cfb:
    def __init__(self, key):
        self.key = SHA256.new(key.encode()).digest()
        self.iv = Random.new().read(AES.block_size)
        self.cipher = AES.new(self.key, AES.MODE_CFB, self.iv)

    def pkcs7_encode(self, data):
        block_size = 16
        padd_len = block_size - len(data) % block_size
        data += ''.join((chr(i) for i in range(1, padd_len + 1)))
        return data

    def pkcs7_decode(self, data):
        padd_len = data[-1]
        return data[:-padd_len]

    def encrypt(self, data):
        return self.iv + self.cipher.encrypt(data)

    def decrypt(self, data):
        #iv = data[:16]
        data = data[16:]
        return self.cipher.decrypt(data)


if __name__ == '__main__':
    aes_256_cfb = aes_cfb('test')
    cipher = aes_256_cfb.encrypt(b'sherlock holo')
    print('cipher len:', len(cipher[16:]))
    print('cipher:', cipher)
    plain_text = aes_256_cfb.decrypt(cipher)
    print('plain text len:', len(plain_text))
    print('plain text:', plain_text)
