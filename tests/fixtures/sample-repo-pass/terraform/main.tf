terraform {
  backend "s3" {
    bucket  = "acme-corp-tfstate"
    key     = "main.tfstate"
    region  = "us-east-1"
    encrypt = true
  }
}
