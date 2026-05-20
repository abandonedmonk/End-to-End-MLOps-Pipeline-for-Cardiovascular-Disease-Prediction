variable "project_name" {
  type = string
}

variable "instance_type" {
  type = string
}

variable "ssh_public_key" {
  type = string
}

variable "your_ip" {
  type = string
}

variable "mlflow_port" {
  type = number
}

variable "api_port" {
  type = number
}

variable "instance_profile_name" {
  type = string
}

variable "user_data_script" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_id" {
  type = string
}

variable "prefect_api_url" {
  type    = string
  default = ""
}

variable "prefect_api_key" {
  type    = string
  default = ""
}